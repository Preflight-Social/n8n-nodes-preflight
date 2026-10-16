import type {
	IDataObject,
	IExecuteFunctions,
	IHookFunctions,
	IHttpRequestMethods,
	IHttpRequestOptions,
	ILoadOptionsFunctions,
	JsonObject,
} from 'n8n-workflow';
import { NodeApiError } from 'n8n-workflow';

type PreflightContext = IExecuteFunctions | ILoadOptionsFunctions | IHookFunctions;

export const DEFAULT_BASE_URL = 'https://preflight.social';

export async function getBaseUrl(this: PreflightContext): Promise<string> {
	const credentials = await this.getCredentials('preflightApi');
	const raw = typeof credentials.baseUrl === 'string' && credentials.baseUrl.trim() !== ''
		? credentials.baseUrl.trim()
		: DEFAULT_BASE_URL;
	return raw.replace(/\/+$/, '').replace(/\/v1$/, '');
}

interface PreflightErrorBody {
	error?: {
		code?: string;
		message?: string;
		field?: string;
		issues?: Array<{ platform?: string; severity?: string; message?: string }>;
		limit?: number;
		upgradeTo?: string;
	};
}

/** Pulls Preflight's `{ error: { code, message } }` out of whatever the HTTP helper threw. */
function preflightErrorOf(error: unknown): PreflightErrorBody['error'] | undefined {
	const candidates: unknown[] = [];
	const e = error as {
		response?: { body?: unknown; data?: unknown };
		cause?: { response?: { body?: unknown; data?: unknown } };
		description?: unknown;
	};
	candidates.push(e?.response?.body, e?.response?.data, e?.cause?.response?.body, e?.cause?.response?.data);
	for (const candidate of candidates) {
		let value = candidate;
		if (typeof value === 'string') {
			try {
				value = JSON.parse(value);
			} catch {
				continue;
			}
		}
		if (value && typeof value === 'object' && 'error' in value) {
			const inner = (value as PreflightErrorBody).error;
			if (inner && typeof inner === 'object') return inner;
		}
	}
	return undefined;
}

function describeIssues(issues: NonNullable<PreflightErrorBody['error']>['issues']): string {
	if (!issues || issues.length === 0) return '';
	return issues
		.map((issue) => `${issue.severity ?? 'error'}${issue.platform ? ` (${issue.platform})` : ''}: ${issue.message ?? ''}`)
		.join('\n');
}

/**
 * One authenticated call to the Preflight REST API.
 *
 * `path` starts after /v1, e.g. `/posts`. Errors come back as NodeApiError
 * carrying Preflight's own code and message, so a refusal such as
 * `validation_failed` or `scheduled_in_past` reads the same as in the docs.
 */
export async function preflightApiRequest(
	this: PreflightContext,
	method: IHttpRequestMethods,
	path: string,
	body?: IDataObject,
	qs?: IDataObject,
	headers?: IDataObject,
	itemIndex?: number,
): Promise<IDataObject> {
	const baseUrl = await getBaseUrl.call(this);
	const options: IHttpRequestOptions = {
		method,
		url: `${baseUrl}/v1${path}`,
		json: true,
		headers: { Accept: 'application/json', ...(headers ?? {}) },
	};
	if (body !== undefined) options.body = body;
	if (qs !== undefined && Object.keys(qs).length > 0) options.qs = qs;

	try {
		const response = (await this.helpers.httpRequestWithAuthentication.call(
			this,
			'preflightApi',
			options,
		)) as IDataObject | string | undefined;
		if (response === undefined || response === '' || response === null) return {};
		if (typeof response === 'string') {
			try {
				return JSON.parse(response) as IDataObject;
			} catch {
				return { response };
			}
		}
		return response;
	} catch (error) {
		const preflight = preflightErrorOf(error);
		if (preflight) {
			const extra: string[] = [];
			if (preflight.code) extra.push(`Code: ${preflight.code}`);
			if (preflight.field) extra.push(`Field: ${preflight.field}`);
			if (preflight.limit !== undefined) extra.push(`Plan allowance: ${preflight.limit}`);
			if (preflight.upgradeTo) extra.push(`Allowed from the ${preflight.upgradeTo} plan`);
			const issues = describeIssues(preflight.issues);
			if (issues) extra.push(issues);
			throw new NodeApiError(this.getNode(), error as JsonObject, {
				message: preflight.message ?? 'Preflight refused the request',
				description: extra.join('\n'),
				itemIndex,
			});
		}
		throw new NodeApiError(this.getNode(), error as JsonObject, { itemIndex });
	}
}

/**
 * A call to Preflight's MCP endpoint with the same API key.
 *
 * Used only for what the REST API does not yet offer to API keys
 * (the queue's next free slot per channel). The result is the tool's
 * structuredContent.
 */
export async function preflightMcpToolCall(
	this: PreflightContext,
	tool: string,
	args: IDataObject,
	itemIndex?: number,
): Promise<IDataObject> {
	const baseUrl = await getBaseUrl.call(this);
	const options: IHttpRequestOptions = {
		method: 'POST',
		url: `${baseUrl}/mcp`,
		json: true,
		headers: { Accept: 'application/json, text/event-stream' },
		body: {
			jsonrpc: '2.0',
			id: 1,
			method: 'tools/call',
			params: { name: tool, arguments: args },
		},
	};

	let response: IDataObject;
	try {
		response = (await this.helpers.httpRequestWithAuthentication.call(
			this,
			'preflightApi',
			options,
		)) as IDataObject;
	} catch (error) {
		throw new NodeApiError(this.getNode(), error as JsonObject, { itemIndex });
	}

	const rpcError = response.error as IDataObject | undefined;
	if (rpcError) {
		throw new NodeApiError(this.getNode(), response as JsonObject, {
			message: String(rpcError.message ?? 'Preflight refused the request'),
			itemIndex,
		});
	}

	const result = (response.result ?? {}) as IDataObject;
	const text = ((result.content as IDataObject[] | undefined) ?? [])
		.map((part) => (typeof part.text === 'string' ? part.text : ''))
		.join('\n');
	if (result.isError === true) {
		throw new NodeApiError(this.getNode(), response as JsonObject, {
			message: text || 'Preflight refused the request',
			itemIndex,
		});
	}
	if (result.structuredContent && typeof result.structuredContent === 'object') {
		return result.structuredContent as IDataObject;
	}
	try {
		return JSON.parse(text) as IDataObject;
	} catch {
		return { result: text };
	}
}

/** Offset of a time zone from UTC at a given instant, in minutes. */
function zoneOffsetMinutes(timeZone: string, at: Date): number {
	const parts = new Intl.DateTimeFormat('en-US', {
		timeZone,
		hourCycle: 'h23',
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
	}).formatToParts(at);
	const get = (type: string) => Number(parts.find((part) => part.type === type)?.value);
	const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'));
	return Math.round((asUtc - at.getTime()) / 60000);
}

/**
 * Any date the node may be handed, as an ISO 8601 instant in UTC, or
 * undefined when it is not a date.
 *
 * A value with a zone (Z, +01:00) or a Date/Luxon object is that instant.
 * A wall-clock value without one ("2026-11-02 09:30", the date picker's
 * "2026-11-02T09:30:00") is read in `timeZone`, the workflow's zone.
 */
export function toUtcInstant(value: unknown, timeZone: string): string | undefined {
	let text: string;
	if (value && typeof value === 'object' && typeof (value as { toISO?: unknown }).toISO === 'function') {
		text = String((value as { toISO: () => string }).toISO());
	} else if (value instanceof Date) {
		text = value.toISOString();
	} else {
		text = String(value ?? '').trim();
	}
	if (text === '') return undefined;

	const match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/.exec(text);
	let date: Date;
	if (match) {
		const [, y, mo, d, h, mi, s] = match;
		const wallAsUtc = Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s ?? 0));
		// Twice: the offset at the guess can differ from the offset at the answer across a DST change.
		let instant = wallAsUtc - zoneOffsetMinutes(timeZone, new Date(wallAsUtc)) * 60000;
		instant = wallAsUtc - zoneOffsetMinutes(timeZone, new Date(instant)) * 60000;
		date = new Date(instant);
	} else {
		date = new Date(text);
	}
	return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}
