import type {
	IDataObject,
	IExecuteFunctions,
	ILoadOptionsFunctions,
	INodeExecutionData,
	INodePropertyOptions,
	INodeType,
	INodeTypeDescription,
	JsonObject,
} from 'n8n-workflow';
import { NodeApiError, NodeConnectionTypes, NodeOperationError, sleep } from 'n8n-workflow';
import { randomUUID } from 'crypto';

import { channelFields, channelOperations } from './descriptions/ChannelDescription';
import { mediaFields, mediaOperations } from './descriptions/MediaDescription';
import { postFields, postOperations } from './descriptions/PostDescription';
import { preflightApiRequest, preflightMcpToolCall, toUtcInstant } from './GenericFunctions';

const PLATFORM_NAMES: Record<string, string> = {
	bluesky: 'Bluesky',
	discord: 'Discord',
	facebook: 'Facebook',
	instagram: 'Instagram',
	linkedin: 'LinkedIn',
	mastodon: 'Mastodon',
	pinterest: 'Pinterest',
	telegram: 'Telegram',
	threads: 'Threads',
	tiktok: 'TikTok',
	tumblr: 'Tumblr',
	twitter: 'X',
	youtube: 'YouTube',
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'avif', 'bmp', 'tif', 'tiff'];
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'm4v', 'webm', 'avi', 'mkv', 'mpeg', 'mpg'];

/** Everything a multiOptions or expression can hand us, as a flat list of strings. */
function toList(value: unknown): string[] {
	if (value === undefined || value === null || value === '') return [];
	if (Array.isArray(value)) return value.flatMap((entry) => toList(entry));
	return String(value)
		.split(',')
		.map((entry) => entry.trim())
		.filter((entry) => entry !== '');
}

/** "bluesky:<uuid>", "<uuid>@bluesky", or a bare network name. */
function parseChannel(
	this: IExecuteFunctions,
	value: string,
	itemIndex: number,
): { platform: string; accountId?: string } {
	const [first, second] = value.split(':').map((part) => part.trim());
	if (second !== undefined) {
		const platform = first.toLowerCase();
		if (!PLATFORM_NAMES[platform] || !UUID.test(second)) {
			throw new NodeOperationError(this.getNode(), `'${value}' is not a channel Preflight knows`, {
				itemIndex,
				description: 'Use "platform:channelId", e.g. "bluesky:3f2c9a1e-…", or pick channels from the list.',
			});
		}
		return { platform, accountId: second };
	}
	const platform = first.toLowerCase();
	if (!PLATFORM_NAMES[platform]) {
		throw new NodeOperationError(this.getNode(), `'${value}' is not a channel Preflight knows`, {
			itemIndex,
			description:
				'A bare channel ID needs its network in front of it, e.g. "bluesky:3f2c9a1e-…". Pick channels from the list to get the right format.',
		});
	}
	return { platform };
}

function parseJsonObject(
	this: IExecuteFunctions,
	value: unknown,
	parameter: string,
	itemIndex: number,
): IDataObject {
	if (value === undefined || value === null || value === '') return {};
	if (typeof value === 'object') return value as IDataObject;
	try {
		const parsed = JSON.parse(String(value));
		if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as IDataObject;
	} catch {
		// Reported below with the parameter's name.
	}
	throw new NodeOperationError(this.getNode(), `'${parameter}' is not a JSON object`, {
		itemIndex,
		description: 'Write it as {"networkName": {"option": "value"}}, e.g. {"youtube": {"categoryId": "22"}}.',
	});
}

/** The per-network options each target carries, from the typed fields and the JSON. */
function optionsFor(this: IExecuteFunctions, platform: string, networkOptions: IDataObject, itemIndex: number): IDataObject {
	const options: IDataObject = {};
	const has = (key: string) => networkOptions[key] !== undefined && networkOptions[key] !== '';

	if (platform === 'youtube') {
		if (has('youtubeTitle')) options.title = networkOptions.youtubeTitle;
		if (has('youtubePrivacy')) options.privacy = networkOptions.youtubePrivacy;
		if (has('youtubeShort')) options.short = networkOptions.youtubeShort;
		if (has('youtubeTags')) options.tags = toList(networkOptions.youtubeTags);
	}
	if (platform === 'tiktok') {
		if (has('tiktokPrivacy')) options.privacy = networkOptions.tiktokPrivacy;
		if (has('tiktokAsDraft')) options.asDraft = networkOptions.tiktokAsDraft;
	}
	if (platform === 'instagram' && has('instagramPlacement')) options.placement = networkOptions.instagramPlacement;
	if (platform === 'pinterest') {
		if (has('pinterestBoardId')) options.boardId = networkOptions.pinterestBoardId;
		if (has('pinterestTitle')) options.title = networkOptions.pinterestTitle;
	}
	if (['youtube', 'facebook', 'instagram'].includes(platform) && has('firstComment')) {
		options.firstComment = networkOptions.firstComment;
	}

	const fromJson = parseJsonObject.call(this, networkOptions.optionsJson, 'Options JSON', itemIndex);
	const extra = fromJson[platform];
	if (extra && typeof extra === 'object' && !Array.isArray(extra)) Object.assign(options, extra as IDataObject);
	return options;
}

function buildTargets(
	this: IExecuteFunctions,
	channels: unknown,
	networkOptions: IDataObject,
	itemIndex: number,
): IDataObject[] {
	const list = toList(channels);
	if (list.length === 0) {
		throw new NodeOperationError(this.getNode(), "No channels in 'Channel Names or IDs'", {
			itemIndex,
			description: 'Pick at least one channel the post should go to.',
		});
	}
	return list.map((value) => {
		const { platform, accountId } = parseChannel.call(this, value, itemIndex);
		const target: IDataObject = { platform, options: optionsFor.call(this, platform, networkOptions, itemIndex) };
		if (accountId) target.accountId = accountId;
		return target;
	});
}

function altTextsOf(value: unknown): Array<string | null> | undefined {
	if (value === undefined || value === null || value === '') return undefined;
	if (Array.isArray(value)) return value.map((entry) => (entry === null || entry === '' ? null : String(entry)));
	return String(value)
		.split(/\r?\n/)
		.map((line) => (line.trim() === '' ? null : line.trim()));
}

/**
 * An instant as Preflight takes it (ISO 8601 in UTC).
 *
 * The date picker gives a wall-clock time without a zone; that is read in
 * the workflow's own time zone, the way n8n shows it.
 */
function toUtcIso(this: IExecuteFunctions, value: unknown, parameter: string, itemIndex: number): string {
	const iso = toUtcInstant(value, this.getTimezone());
	if (!iso) {
		throw new NodeOperationError(this.getNode(), `'${parameter}' is not a date and time`, {
			itemIndex,
			description: 'Use an ISO 8601 value such as 2026-11-02T09:30:00Z, or pick a time in the date picker.',
		});
	}
	return iso;
}

function guessKind(mimeType: string | undefined, name: string | undefined): 'image' | 'video' | undefined {
	const mime = (mimeType ?? '').toLowerCase();
	if (mime.startsWith('image/')) return 'image';
	if (mime.startsWith('video/')) return 'video';
	const extension = (name ?? '').split('?')[0].split('#')[0].split('.').pop()?.toLowerCase() ?? '';
	if (IMAGE_EXTENSIONS.includes(extension)) return 'image';
	if (VIDEO_EXTENSIONS.includes(extension)) return 'video';
	return undefined;
}

/** PUT to a signed storage URL. Unauthenticated on purpose: the URL is the credential. */
async function putToSignedUrl(
	this: IExecuteFunctions,
	url: string,
	data: Buffer,
	headers: IDataObject,
): Promise<string | undefined> {
	const response = (await this.helpers.httpRequest({
		method: 'PUT',
		url,
		body: data,
		headers: headers as Record<string, string>,
		json: false,
		returnFullResponse: true,
		timeout: 10 * 60 * 1000,
	})) as { headers?: Record<string, string | string[] | undefined> };
	const etag = response.headers?.etag ?? response.headers?.ETag;
	return Array.isArray(etag) ? etag[0] : etag;
}

async function waitForMedia(
	this: IExecuteFunctions,
	mediaId: string,
	timeoutSeconds: number,
	itemIndex: number,
): Promise<IDataObject> {
	const deadline = Date.now() + timeoutSeconds * 1000;
	let delay = 2000;
	for (;;) {
		const media = await preflightApiRequest.call(this, 'GET', `/media/${mediaId}`, undefined, undefined, undefined, itemIndex);
		if (media.status === 'ready') return media;
		if (media.status === 'failed' || media.status === 'deleted') {
			throw new NodeOperationError(this.getNode(), `Preflight could not take the file: ${String(media.error ?? media.status)}`, {
				itemIndex,
				description: 'Check that the URL is public and the file is an image or video the networks accept.',
			});
		}
		if (Date.now() + delay > deadline) {
			throw new NodeOperationError(this.getNode(), `The file was still ${String(media.status)} after ${timeoutSeconds} seconds`, {
				itemIndex,
				description: `Media ID ${mediaId}. Raise 'Wait Timeout (Seconds)', or turn off 'Wait Until Ready' and check it later with Media → Get.`,
			});
		}
		await sleep(delay);
		delay = Math.min(delay * 1.5, 10000);
	}
}

export class Preflight implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'Preflight',
		name: 'preflight',
		icon: { light: 'file:../../icons/preflight.svg', dark: 'file:../../icons/preflight.dark.svg' },
		group: ['output'],
		version: 1,
		subtitle: '={{$parameter["operation"] + ": " + $parameter["resource"]}}',
		description:
			'Check posts against every network’s rules, then schedule or publish them to YouTube, TikTok, Instagram, Facebook, Threads, LinkedIn, Pinterest, Bluesky, Mastodon, Telegram, Discord and Tumblr',
		defaults: {
			name: 'Preflight',
		},
		usableAsTool: true,
		inputs: [NodeConnectionTypes.Main],
		outputs: [NodeConnectionTypes.Main],
		credentials: [
			{
				name: 'preflightApi',
				required: true,
			},
		],
		properties: [
			{
				displayName: 'Resource',
				name: 'resource',
				type: 'options',
				noDataExpression: true,
				options: [
					{ name: 'Channel', value: 'channel' },
					{ name: 'Media', value: 'media' },
					{ name: 'Post', value: 'post' },
				],
				default: 'post',
			},
			...channelOperations,
			...channelFields,
			...mediaOperations,
			...mediaFields,
			...postOperations,
			...postFields,
		],
	};

	methods = {
		loadOptions: {
			async getChannels(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const response = await preflightApiRequest.call(this, 'GET', '/oauth/accounts');
				return ((response.data as IDataObject[] | undefined) ?? []).map((account) => {
					const platform = String(account.platform);
					const label = String(account.displayName || account.username || account.id);
					const state = account.needsReconnect ? ' (needs reconnecting)' : account.paused ? ' (paused by plan)' : '';
					return {
						name: `${PLATFORM_NAMES[platform] ?? platform} · ${label}${state}`,
						value: `${platform}:${String(account.id)}`,
					};
				});
			},
			async getChannelIds(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
				const response = await preflightApiRequest.call(this, 'GET', '/oauth/accounts');
				return ((response.data as IDataObject[] | undefined) ?? []).map((account) => {
					const platform = String(account.platform);
					const label = String(account.displayName || account.username || account.id);
					return { name: `${PLATFORM_NAMES[platform] ?? platform} · ${label}`, value: String(account.id) };
				});
			},
		},
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];

		for (let i = 0; i < items.length; i++) {
			let failure: unknown;
			try {
				const resource = this.getNodeParameter('resource', i) as string;
				const operation = this.getNodeParameter('operation', i) as string;
				const push = (data: IDataObject | IDataObject[]) => {
					for (const json of Array.isArray(data) ? data : [data]) {
						returnData.push({ json, pairedItem: { item: i } });
					}
				};

				// ------------------------------------------------------------
				//   Channel
				// ------------------------------------------------------------
				if (resource === 'channel') {
					if (operation === 'getAll') {
						const response = await preflightApiRequest.call(this, 'GET', '/oauth/accounts', undefined, undefined, undefined, i);
						const filters = this.getNodeParameter('filters', i, {}) as IDataObject;
						let channels = (response.data as IDataObject[] | undefined) ?? [];
						if (filters.platform) channels = channels.filter((c) => c.platform === filters.platform);
						if (filters.usableOnly !== false && filters.usableOnly !== undefined) {
							channels = channels.filter((c) => !c.needsReconnect && !c.paused);
						}
						const returnAll = this.getNodeParameter('returnAll', i, false) as boolean;
						if (!returnAll) channels = channels.slice(0, this.getNodeParameter('limit', i, 50) as number);
						push(channels);
						continue;
					}

					if (operation === 'getNextQueueTimes') {
						const channelIds = toList(this.getNodeParameter('channelIds', i, []));
						const args: IDataObject = channelIds.length > 0 ? { channelIds } : {};
						const result = await preflightMcpToolCall.call(this, 'next_queue_times', args, i);
						const timezone = result.timezone;
						push(((result.channels as IDataObject[] | undefined) ?? []).map((row) => ({ ...row, timezone })));
						continue;
					}
				}

				// ------------------------------------------------------------
				//   Media
				// ------------------------------------------------------------
				if (resource === 'media') {
					if (operation === 'get') {
						const mediaId = this.getNodeParameter('mediaId', i) as string;
						push(await preflightApiRequest.call(this, 'GET', `/media/${encodeURIComponent(mediaId)}`, undefined, undefined, undefined, i));
						continue;
					}

					if (operation === 'delete') {
						const mediaId = this.getNodeParameter('mediaId', i) as string;
						await preflightApiRequest.call(this, 'DELETE', `/media/${encodeURIComponent(mediaId)}`, undefined, undefined, undefined, i);
						push({ deleted: true, id: mediaId });
						continue;
					}

					if (operation === 'upload') {
						const source = this.getNodeParameter('source', i) as string;
						const kindParameter = this.getNodeParameter('kind', i) as string;
						const waitUntilReady = this.getNodeParameter('waitUntilReady', i, true) as boolean;
						const options = this.getNodeParameter('options', i, {}) as IDataObject;

						const body: IDataObject = {};
						for (const key of ['durationSeconds', 'width', 'height']) {
							if (typeof options[key] === 'number' && (options[key] as number) > 0) body[key] = options[key];
						}
						if (options.fileName) body.filename = options.fileName;

						let data: Buffer | undefined;
						let mimeType = options.mimeType ? String(options.mimeType) : undefined;
						let nameForKind: string | undefined;

						if (source === 'url') {
							const sourceUrl = (this.getNodeParameter('sourceUrl', i) as string).trim();
							if (!/^https:\/\//i.test(sourceUrl)) {
								throw new NodeOperationError(this.getNode(), "'File URL' must be a public https address", { itemIndex: i });
							}
							body.sourceUrl = sourceUrl;
							nameForKind = sourceUrl;
						} else {
							const binaryPropertyName = this.getNodeParameter('binaryPropertyName', i) as string;
							const binary = this.helpers.assertBinaryData(i, binaryPropertyName);
							// The object rather than the name: works in both of n8n's binary modes.
							data = await this.helpers.getBinaryDataBuffer(i, binary);
							mimeType = mimeType ?? binary.mimeType;
							nameForKind = binary.fileName;
							if (!body.filename && binary.fileName) body.filename = binary.fileName;
							body.sizeBytes = data.length;
						}

						const kind = kindParameter === 'auto' ? guessKind(mimeType, String(body.filename ?? nameForKind ?? '')) : kindParameter;
						if (!kind) {
							throw new NodeOperationError(this.getNode(), 'Could not tell whether the file is an image or a video', {
								itemIndex: i,
								description: "Set 'Kind' to Image or Video, or add the 'MIME Type' option.",
							});
						}
						body.kind = kind;
						if (mimeType && mimeType.toLowerCase().startsWith(`${kind}/`)) body.mimeType = mimeType;

						const created = await preflightApiRequest.call(this, 'POST', '/media', body, undefined, undefined, i);
						// The answer is { id, status, upload: { type, url, headers | partSize, parts } };
						// the older documented shape { media, upload: { mode, uploadUrl } } is read too.
						let media = (created.media as IDataObject | undefined) ?? created;
						const upload = (created.upload as IDataObject | undefined) ?? {};
						const uploadType = upload.type ?? upload.mode;
						const uploadUrl = upload.url ?? upload.uploadUrl;
						const mediaId = String(media.id);

						if (data) {
							const headers = (upload.headers as IDataObject | undefined) ?? {};
							if (uploadType === 'single' && typeof uploadUrl === 'string') {
								await putToSignedUrl.call(this, uploadUrl, data, headers);
								media = await preflightApiRequest.call(this, 'POST', `/media/${mediaId}/uploaded`, {}, undefined, undefined, i);
							} else if (uploadType === 'multipart' && Array.isArray(upload.parts)) {
								const partSize = Number(upload.partSize);
								const parts: IDataObject[] = [];
								for (const part of upload.parts as IDataObject[]) {
									const partNumber = Number(part.partNumber);
									const slice = data.subarray((partNumber - 1) * partSize, partNumber * partSize);
									const etag = await putToSignedUrl.call(this, String(part.url), slice, headers);
									if (!etag) {
										throw new NodeOperationError(this.getNode(), `Storage gave no ETag for part ${partNumber}`, {
											itemIndex: i,
											description: 'Run the node again; a new upload is started each time.',
										});
									}
									parts.push({ partNumber, etag });
								}
								media = await preflightApiRequest.call(this, 'POST', `/media/${mediaId}/complete`, { parts }, undefined, undefined, i);
							} else {
								throw new NodeOperationError(this.getNode(), `Preflight answered with an upload mode this node does not know: ${String(uploadType)}`, { itemIndex: i });
							}
						}

						if (waitUntilReady && media.status !== 'ready') {
							const timeout = typeof options.waitTimeout === 'number' ? options.waitTimeout : 600;
							media = await waitForMedia.call(this, mediaId, timeout, i);
						}
						push(media);
						continue;
					}
				}

				// ------------------------------------------------------------
				//   Post
				// ------------------------------------------------------------
				if (resource === 'post') {
					if (operation === 'validate' || operation === 'create') {
						const content = this.getNodeParameter('content', i, '') as string;
						const additional = this.getNodeParameter('additionalFields', i, {}) as IDataObject;
						const networkOptions = this.getNodeParameter('networkOptions', i, {}) as IDataObject;
						const body: IDataObject = {
							content,
							targets: buildTargets.call(this, this.getNodeParameter('channels', i), networkOptions, i),
						};
						const mediaIds = toList(additional.mediaIds);
						if (mediaIds.length > 0) body.mediaIds = mediaIds;
						const altTexts = altTextsOf(additional.altTexts);
						if (altTexts) body.altTexts = altTexts;
						if (additional.linkUrl) body.linkUrl = String(additional.linkUrl).trim();

						if (operation === 'validate') {
							const result = await preflightApiRequest.call(this, 'POST', '/platforms/validate', body, undefined, undefined, i);
							const issues = (result.issues as IDataObject[] | undefined) ?? [];
							const errors = issues.filter((issue) => issue.severity === 'error');
							const warnings = issues.filter((issue) => issue.severity === 'warning');
							if (this.getNodeParameter('failOnErrors', i, false) && errors.length > 0) {
								throw new NodeOperationError(this.getNode(), `${errors.length} network rule(s) would refuse this post`, {
									itemIndex: i,
									description: errors
										.map((issue) => `${issue.platform ? `${PLATFORM_NAMES[String(issue.platform)] ?? issue.platform}: ` : ''}${String(issue.message)}`)
										.join('\n'),
								});
							}
							push({ ok: result.ok ?? errors.length === 0, errorCount: errors.length, warningCount: warnings.length, issues });
							continue;
						}

						const when = this.getNodeParameter('when', i) as string;
						if (when === 'draft') body.saveAsDraft = true;
						if (when === 'queue') body.queue = true;
						if (when === 'scheduled') body.scheduledAt = toUtcIso.call(this, this.getNodeParameter('scheduledAt', i), 'Scheduled At', i);
						if (when === 'scheduledLocal') {
							const local = String(this.getNodeParameter('scheduledLocal', i)).trim().slice(0, 16);
							if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) {
								throw new NodeOperationError(this.getNode(), "'Local Time' must look like 2026-11-02T09:30", { itemIndex: i });
							}
							body.scheduledLocal = local;
						}
						if (when === 'publishNow') {
							if (this.getNodeParameter('confirmPublishNow', i, false) !== true) {
								throw new NodeOperationError(this.getNode(), 'Publishing now needs confirming', {
									itemIndex: i,
									description: "Turn on 'Confirm Publish Now' if this post should go live the moment the node runs, or choose another option in 'When'.",
								});
							}
							body.publishNow = true;
						}

						let idempotencyKey = String(this.getNodeParameter('idempotencyKey', i, '') ?? '').trim();
						if (idempotencyKey === '') idempotencyKey = `n8n-${randomUUID()}`;
						if (idempotencyKey.length < 8) idempotencyKey = `n8n-key-${idempotencyKey}`;
						if (idempotencyKey.length > 200) {
							throw new NodeOperationError(this.getNode(), "'Idempotency Key' is longer than 200 characters", {
								itemIndex: i,
								description: 'Use a shorter stable value, such as a row ID or a hash of the link.',
							});
						}

						push(await preflightApiRequest.call(this, 'POST', '/posts', body, undefined, { 'Idempotency-Key': idempotencyKey }, i));
						continue;
					}

					const postIdOf = () => encodeURIComponent(String(this.getNodeParameter('postId', i)).trim());

					if (operation === 'get') {
						const postId = postIdOf();
						push(await preflightApiRequest.call(this, 'GET', `/posts/${postId}`, undefined, undefined, undefined, i));
						continue;
					}

					if (operation === 'delete') {
						const postId = postIdOf();
						await preflightApiRequest.call(this, 'DELETE', `/posts/${postId}`, undefined, undefined, undefined, i);
						push({ deleted: true, id: decodeURIComponent(postId) });
						continue;
					}

					if (operation === 'retry') {
						const postId = postIdOf();
						const targetId = (this.getNodeParameter('targetId', i, '') as string).trim();
						const path = targetId ? `/posts/${postId}/targets/${encodeURIComponent(targetId)}/retry` : `/posts/${postId}/retry`;
						push(await preflightApiRequest.call(this, 'POST', path, {}, undefined, undefined, i));
						continue;
					}

					if (operation === 'update') {
						const postId = postIdOf();
						const fields = this.getNodeParameter('updateFields', i, {}) as IDataObject;
						const networkOptions = this.getNodeParameter('networkOptions', i, {}) as IDataObject;
						const body: IDataObject = {};
						if (fields.content !== undefined) body.content = fields.content;
						if (fields.linkUrl !== undefined) body.linkUrl = String(fields.linkUrl).trim() === '' ? null : String(fields.linkUrl).trim();
						if (fields.mediaIds !== undefined) body.mediaIds = toList(fields.mediaIds);
						const altTexts = altTextsOf(fields.altTexts);
						if (altTexts) body.altTexts = altTexts;
						if (fields.scheduledAt) body.scheduledAt = toUtcIso.call(this, fields.scheduledAt, 'Scheduled At', i);
						if (fields.scheduledLocal) body.scheduledLocal = String(fields.scheduledLocal).trim().slice(0, 16);
						if (fields.queue === true) body.queue = true;
						if (fields.keepApproval === true) body.keepApproval = true;
						if (fields.channels !== undefined && toList(fields.channels).length > 0) {
							body.targets = buildTargets.call(this, fields.channels, networkOptions, i);
						}
						if (Object.keys(body).length === 0) {
							throw new NodeOperationError(this.getNode(), 'Nothing to update', {
								itemIndex: i,
								description: "Add at least one field under 'Update Fields'.",
							});
						}
						push(await preflightApiRequest.call(this, 'PATCH', `/posts/${postId}`, body, undefined, undefined, i));
						continue;
					}

					if (operation === 'getAll') {
						const returnAll = this.getNodeParameter('returnAll', i, false) as boolean;
						const limit = returnAll ? Infinity : (this.getNodeParameter('limit', i, 50) as number);
						const filters = this.getNodeParameter('filters', i, {}) as IDataObject;
						const qs: IDataObject = {};
						if (filters.status) qs.status = filters.status;
						if (filters.from) qs.from = toUtcIso.call(this, filters.from, 'From', i);
						if (filters.to) qs.to = toUtcIso.call(this, filters.to, 'To', i);
						if (filters.days) qs.days = filters.days;

						// The status is also checked here: the API documents the filter, but a
						// server that ignores it would otherwise hand back every post.
						const wanted = filters.status ? String(filters.status) : undefined;
						const posts: IDataObject[] = [];
						let cursor: string | undefined;
						let pages = 0;
						do {
							const pageSize = wanted ? 200 : Math.min(500, limit - posts.length);
							const page = await preflightApiRequest.call(
								this,
								'GET',
								'/posts',
								undefined,
								{ ...qs, limit: pageSize, ...(cursor ? { before: cursor } : {}) },
								undefined,
								i,
							);
							const rows = ((page.data as IDataObject[] | undefined) ?? []) as IDataObject[];
							posts.push(...(wanted ? rows.filter((post) => post.status === wanted) : rows));
							// The server answers `nextBefore`; the OpenAPI file calls it `nextCursor`.
							const next = page.nextBefore ?? page.nextCursor;
							cursor = typeof next === 'string' && next !== '' ? next : undefined;
							pages++;
						} while (cursor && posts.length < limit && pages < 100);
						push(posts.slice(0, limit === Infinity ? undefined : limit));
						continue;
					}
				}

				throw new NodeOperationError(this.getNode(), `The operation '${operation}' is not known for '${resource}'`, { itemIndex: i });
			} catch (error) {
				failure = error;
			}

			if (failure === undefined) continue;
			if (this.continueOnFail()) {
				returnData.push({
					json: { error: (failure as Error).message, description: (failure as NodeApiError).description ?? undefined },
					pairedItem: { item: i },
				});
				continue;
			}
			// Already carries the item index and Preflight's own message.
			if (failure instanceof NodeApiError || failure instanceof NodeOperationError) throw failure;
			throw new NodeApiError(this.getNode(), failure as JsonObject, { itemIndex: i });
		}

		return [returnData];
	}
}
