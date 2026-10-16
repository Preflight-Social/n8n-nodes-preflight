import type {
	IDataObject,
	IHookFunctions,
	INodeType,
	INodeTypeDescription,
	IWebhookFunctions,
	IWebhookResponseData,
} from 'n8n-workflow';
import { NodeApiError, NodeConnectionTypes, NodeOperationError } from 'n8n-workflow';
import { createHmac, timingSafeEqual } from 'crypto';

import { preflightApiRequest } from '../Preflight/GenericFunctions';

/** How far the signed timestamp may stray from now, as Preflight's own reference check allows. */
const TIMESTAMP_TOLERANCE_SECONDS = 300;

function headerOf(headers: IDataObject, name: string): string | undefined {
	const value = headers[name] ?? headers[name.toLowerCase()];
	if (Array.isArray(value)) return value[0] as string;
	return typeof value === 'string' ? value : undefined;
}

/**
 * Checks `t=<unix seconds>,v2=<hex>`, the HMAC-SHA256 of `${t}.${body}`
 * with the secret Preflight returned when the webhook was registered.
 */
export function verifyPreflightSignature(
	rawBody: string,
	secret: string,
	presented: string,
	now = Math.floor(Date.now() / 1000),
): boolean {
	const match = /(?:^|,)t=(\d+)(?:,|$)/.exec(presented);
	const t = Number(match?.[1]);
	if (!Number.isFinite(t) || Math.abs(now - t) > TIMESTAMP_TOLERANCE_SECONDS) return false;
	const mac = createHmac('sha256', secret).update(`${t}.${rawBody}`).digest('hex');
	const expected = Buffer.from(`t=${t},v2=${mac}`);
	const actual = Buffer.from(presented);
	return expected.length === actual.length && timingSafeEqual(expected, actual);
}

export class PreflightTrigger implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'Preflight Trigger',
		name: 'preflightTrigger',
		icon: { light: 'file:../../icons/preflight.svg', dark: 'file:../../icons/preflight.dark.svg' },
		group: ['trigger'],
		version: 1,
		subtitle: '={{$parameter["events"].join(", ")}}',
		description: 'Starts the workflow when a Preflight post is published or fails on a network',
		defaults: {
			name: 'Preflight Trigger',
		},
		inputs: [],
		outputs: [NodeConnectionTypes.Main],
		credentials: [
			{
				name: 'preflightApi',
				required: true,
			},
		],
		webhooks: [
			{
				name: 'default',
				httpMethod: 'POST',
				responseMode: 'onReceived',
				// Empty, so n8n answers with the node's own webhookResponse.
				responseData: '',
				path: 'webhook',
			},
		],
		properties: [
			{
				displayName:
					'Preflight only delivers to a public https address. On a local n8n, set WEBHOOK_URL to a tunnel such as Cloudflare Tunnel or ngrok. The API key needs the webhooks:read and webhooks:write scopes.',
				name: 'notice',
				type: 'notice',
				default: '',
			},
			{
				displayName: 'Events',
				name: 'events',
				type: 'multiOptions',
				required: true,
				default: ['post.failed'],
				options: [
					{
						name: 'Post Failed',
						value: 'post.failed',
						description: 'A network refused the post and Preflight has stopped retrying it. Sent once per channel.',
					},
					{
						name: 'Post Published',
						value: 'post.published',
						description: 'The post is live on a network, with its link. Sent once per channel.',
					},
				],
			},
		],
	};

	webhookMethods = {
		default: {
			async checkExists(this: IHookFunctions): Promise<boolean> {
				const staticData = this.getWorkflowStaticData('node');
				if (!staticData.webhookId) return false;

				const webhookUrl = this.getNodeWebhookUrl('default');
				const events = [...(this.getNodeParameter('events') as string[])].sort();
				const response = await preflightApiRequest.call(this, 'GET', '/workspace/webhooks');
				const existing = ((response.data as IDataObject[] | undefined) ?? []).find(
					(hook) => hook.id === staticData.webhookId,
				);

				const sameEvents =
					existing !== undefined &&
					JSON.stringify([...((existing.events as string[] | undefined) ?? [])].sort()) === JSON.stringify(events);

				if (existing && existing.url === webhookUrl && existing.active !== false && sameEvents) return true;

				// Gone, or pointing somewhere else: remove what is left so create() starts clean.
				if (existing) {
					await preflightApiRequest.call(this, 'DELETE', `/workspace/webhooks/${String(existing.id)}`);
				}
				delete staticData.webhookId;
				delete staticData.webhookSecret;
				return false;
			},

			async create(this: IHookFunctions): Promise<boolean> {
				const webhookUrl = this.getNodeWebhookUrl('default') as string;
				const events = this.getNodeParameter('events') as string[];

				if (!/^https:\/\//i.test(webhookUrl)) {
					throw new NodeOperationError(this.getNode(), 'Preflight only delivers webhooks to https addresses', {
						description: `This n8n gives ${webhookUrl}. Set WEBHOOK_URL to a public https address (for example a Cloudflare Tunnel or ngrok URL) and activate the workflow again.`,
					});
				}

				const response = await preflightApiRequest.call(this, 'POST', '/workspace/webhooks', {
					url: webhookUrl,
					events,
				});

				if (!response.id || !response.secret) {
					throw new NodeApiError(this.getNode(), response as never, {
						message: 'Preflight did not return a webhook ID and secret',
					});
				}

				const staticData = this.getWorkflowStaticData('node');
				staticData.webhookId = response.id;
				staticData.webhookSecret = response.secret;
				return true;
			},

			async delete(this: IHookFunctions): Promise<boolean> {
				const staticData = this.getWorkflowStaticData('node');
				if (!staticData.webhookId) return true;

				let failure: NodeApiError | undefined;
				try {
					await preflightApiRequest.call(this, 'DELETE', `/workspace/webhooks/${String(staticData.webhookId)}`);
				} catch (error) {
					failure = error as NodeApiError;
				}
				// A 404 means it was already removed in Preflight's settings: nothing left to clean up.
				if (failure && failure.httpCode !== '404') throw failure;

				delete staticData.webhookId;
				delete staticData.webhookSecret;
				return true;
			},
		},
	};

	async webhook(this: IWebhookFunctions): Promise<IWebhookResponseData> {
		const request = this.getRequestObject();
		const headers = this.getHeaderData() as IDataObject;
		const body = this.getBodyData() as IDataObject;

		// Always checked: the webhook URL is public, and without this anyone who
		// learned it could start the workflow with a made-up event.
		const secret = this.getWorkflowStaticData('node').webhookSecret as string | undefined;
		const presented =
			headerOf(headers, 'x-preflight-signature-v2') ?? headerOf(headers, 'x-schedulr-signature-v2');
		const rawBody = request.rawBody ? request.rawBody.toString('utf8') : JSON.stringify(body);

		if (!secret || !presented || !verifyPreflightSignature(rawBody, secret, presented)) {
			const response = this.getResponseObject();
			response.status(401).json({ error: 'Signature did not verify' });
			return { noWebhookResponse: true };
		}

		const event = String(body.event ?? headerOf(headers, 'x-preflight-event') ?? '');
		const events = this.getNodeParameter('events') as string[];
		if (events.length > 0 && !events.includes(event)) {
			return { webhookResponse: { received: true, ignored: event } };
		}

		const data = (body.data as IDataObject | undefined) ?? {};
		return {
			// Preflight only looks at the status code.
			webhookResponse: { received: true },
			workflowData: [
				this.helpers.returnJsonArray({
					event,
					deliveryId: body.id ?? headerOf(headers, 'x-preflight-id'),
					createdAt: body.createdAt,
					...data,
				}),
			],
		};
	}
}
