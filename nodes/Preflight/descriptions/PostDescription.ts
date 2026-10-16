import type { INodeProperties } from 'n8n-workflow';

const showForPost = { resource: ['post'] };

export const postOperations: INodeProperties[] = [
	{
		displayName: 'Operation',
		name: 'operation',
		type: 'options',
		noDataExpression: true,
		displayOptions: { show: showForPost },
		options: [
			{
				name: 'Create',
				value: 'create',
				description: 'Create a new post as a draft, at a time, in the queue, or published now',
				action: 'Create a post',
			},
			{
				name: 'Delete',
				value: 'delete',
				description: 'Delete a draft or cancel a scheduled post. What already went out stays on the networks.',
				action: 'Delete a post',
			},
			{
				name: 'Get',
				value: 'get',
				description: 'Get a post and what happened on every network',
				action: 'Get a post',
			},
			{
				name: 'Get Many',
				value: 'getAll',
				description: 'List posts with their per-network state',
				action: 'Get many posts',
			},
			{
				name: 'Retry',
				value: 'retry',
				description: 'Send the post again to the networks where it failed',
				action: 'Retry a post',
			},
			{
				name: 'Update',
				value: 'update',
				description: 'Change the text, files, time or networks of a post that has not gone out',
				action: 'Update a post',
			},
			{
				name: 'Validate',
				value: 'validate',
				description: 'Check a post against every network’s publishing rules without creating anything',
				action: 'Validate a post',
			},
		],
		default: 'create',
	},
];

/** Per-network settings, shared by Validate, Create and Update. */
const networkOptions: INodeProperties = {
	displayName: 'Network Options',
	name: 'networkOptions',
	type: 'collection',
	placeholder: 'Add Network Option',
	default: {},
	options: [
		{
			displayName: 'First Comment',
			name: 'firstComment',
			type: 'string',
			typeOptions: { rows: 2 },
			default: '',
			description: 'Posted as the first comment on YouTube, Facebook and Instagram',
		},
		{
			displayName: 'Instagram Placement',
			name: 'instagramPlacement',
			type: 'options',
			default: 'feed',
			options: [
				{ name: 'Feed', value: 'feed' },
				{ name: 'Reel', value: 'reel' },
				{ name: 'Story', value: 'story' },
			],
		},
		{
			displayName: 'Options JSON',
			name: 'optionsJson',
			type: 'json',
			default: '{}',
			placeholder: 'e.g. {"youtube": {"categoryId": "22"}, "bluesky": {"caption": "Shorter text"}}',
			description:
				'Any per-network option, keyed by network name. Merged over the fields above. See https://preflight.social/docs/network-options.',
		},
		{
			displayName: 'Pinterest Board ID',
			name: 'pinterestBoardId',
			type: 'string',
			default: '',
			placeholder: 'e.g. 1129699956470022291',
			description: 'Required for Pinterest. Find it in Preflight’s composer or the boards endpoint.',
		},
		{
			displayName: 'Pinterest Title',
			name: 'pinterestTitle',
			type: 'string',
			default: '',
		},
		{
			displayName: 'TikTok Privacy',
			name: 'tiktokPrivacy',
			type: 'options',
			default: 'SELF_ONLY',
			options: [
				{ name: 'Everyone', value: 'PUBLIC_TO_EVERYONE' },
				{ name: 'Followers', value: 'FOLLOWER_OF_CREATOR' },
				{ name: 'Friends', value: 'MUTUAL_FOLLOW_FRIENDS' },
				{ name: 'Only Me', value: 'SELF_ONLY' },
			],
			description: 'Required for TikTok. The levels on offer depend on the creator account.',
		},
		{
			displayName: 'TikTok to Inbox',
			name: 'tiktokAsDraft',
			type: 'boolean',
			default: false,
			description: 'Whether to send the video to the creator’s TikTok inbox to finish in the app, instead of posting it',
		},
		{
			displayName: 'YouTube Privacy',
			name: 'youtubePrivacy',
			type: 'options',
			default: 'public',
			options: [
				{ name: 'Private', value: 'private' },
				{ name: 'Public', value: 'public' },
				{ name: 'Unlisted', value: 'unlisted' },
			],
		},
		{
			displayName: 'YouTube Short',
			name: 'youtubeShort',
			type: 'boolean',
			default: false,
			description: 'Whether to publish a vertical video as a Short',
		},
		{
			displayName: 'YouTube Tags',
			name: 'youtubeTags',
			type: 'string',
			default: '',
			placeholder: 'e.g. tutorial, automation, n8n',
			description: 'Comma-separated',
		},
		{
			displayName: 'YouTube Title',
			name: 'youtubeTitle',
			type: 'string',
			default: '',
			description: 'Required for YouTube, up to 100 characters',
		},
	],
};

const channelsField = (operations: string[], required: boolean): INodeProperties => ({
	displayName: 'Channel Names or IDs',
	name: 'channels',
	type: 'multiOptions',
	typeOptions: { loadOptionsMethod: 'getChannels' },
	required,
	default: [],
	displayOptions: { show: { ...showForPost, operation: operations } },
	description: 'Where the post goes. Choose from the list, or specify values using an <a href="https://docs.n8n.io/code/expressions/">expression</a>: "platform:channelId" (e.g. "bluesky:3f2c…") or just the network name (e.g. "mastodon") when the workspace has one channel there. Choose from the list, or specify IDs using an <a href="https://docs.n8n.io/code/expressions/">expression</a>.',
});

export const postFields: INodeProperties[] = [
	// ----------------------------------
	//     post:create / validate
	// ----------------------------------
	channelsField(['create', 'validate'], true),
	{
		displayName: 'Text',
		name: 'content',
		type: 'string',
		typeOptions: { rows: 5 },
		default: '',
		displayOptions: { show: { ...showForPost, operation: ['create', 'validate'] } },
		description: 'The caption. On YouTube it is the description unless set otherwise in the options.',
	},
	{
		displayName: 'When',
		name: 'when',
		type: 'options',
		noDataExpression: true,
		default: 'draft',
		displayOptions: { show: { ...showForPost, operation: ['create'] } },
		options: [
			{
				name: 'Draft (Save for Review)',
				value: 'draft',
				description: 'Park it in Preflight for a person to review. Needs only posts:write.',
			},
			{
				name: 'Publish Now',
				value: 'publishNow',
				description: 'Goes live on every network straight away',
			},
			{
				name: 'Queue (Next Free Slot)',
				value: 'queue',
				description: 'Each channel takes its next slot from its posting schedule',
			},
			{
				name: 'Scheduled Local Time per Channel',
				value: 'scheduledLocal',
				description: 'The same wall-clock time, read in each channel’s own time zone',
			},
			{
				name: 'Scheduled Time',
				value: 'scheduled',
				description: 'One moment for every channel',
			},
		],
	},
	{
		displayName: 'Scheduled At',
		name: 'scheduledAt',
		type: 'dateTime',
		required: true,
		default: '',
		displayOptions: { show: { ...showForPost, operation: ['create'], when: ['scheduled'] } },
		description: 'More than five minutes in the past is refused, so an old item can never go out by mistake',
	},
	{
		displayName: 'Local Time',
		name: 'scheduledLocal',
		type: 'string',
		required: true,
		default: '',
		placeholder: 'e.g. 2026-11-02T09:30',
		displayOptions: { show: { ...showForPost, operation: ['create'], when: ['scheduledLocal'] } },
		description: 'Wall-clock time as YYYY-MM-DDTHH:mm, without a zone',
	},
	{
		displayName: 'Confirm Publish Now',
		name: 'confirmPublishNow',
		type: 'boolean',
		default: false,
		displayOptions: { show: { ...showForPost, operation: ['create'], when: ['publishNow'] } },
		description:
			'Whether you really want this to go live on every chosen network the moment the node runs. Needed so a test run cannot publish by accident.',
	},
	{
		displayName: 'Idempotency Key',
		name: 'idempotencyKey',
		type: 'string',
		default: '={{ $execution.id }}-{{ $itemIndex }}',
		displayOptions: { show: { ...showForPost, operation: ['create'] } },
		description:
			'A retried request with the same key returns the first post instead of creating a second. Use something stable per piece of content, e.g. an RSS item’s link or a sheet row ID. Leave empty to generate a random one.',
	},
	{
		displayName: 'Additional Fields',
		name: 'additionalFields',
		type: 'collection',
		placeholder: 'Add Field',
		default: {},
		displayOptions: { show: { ...showForPost, operation: ['create', 'validate'] } },
		options: [
			{
				displayName: 'Alt Texts',
				name: 'altTexts',
				type: 'string',
				typeOptions: { rows: 3 },
				default: '',
				description: 'One line per file, in the same order as the media IDs. An empty line means no alt text for that file.',
			},
			{
				displayName: 'Link URL',
				name: 'linkUrl',
				type: 'string',
				default: '',
				placeholder: 'e.g. https://example.com/blog/new-post',
				description: 'Placed the way each network takes a link: in the text, as a card, or not at all where links are not allowed',
			},
			{
				displayName: 'Media IDs',
				name: 'mediaIds',
				type: 'string',
				default: '',
				placeholder: 'e.g. 1f0c2b7e-…, 8a9d3c4f-…',
				description: 'Comma-separated IDs from Media → Upload, in display order. The files must be ready.',
			},
		],
	},
	{
		...networkOptions,
		displayOptions: { show: { ...showForPost, operation: ['create', 'validate'] } },
	},
	{
		displayName: 'Fail on Errors',
		name: 'failOnErrors',
		type: 'boolean',
		default: false,
		displayOptions: { show: { ...showForPost, operation: ['validate'] } },
		description:
			'Whether to stop the workflow when any network would refuse the post. Off: the result has ok and issues to branch on.',
	},

	// ----------------------------------
	//     post:get / delete / retry / update
	// ----------------------------------
	{
		displayName: 'Post ID',
		name: 'postId',
		type: 'string',
		required: true,
		default: '',
		placeholder: 'e.g. 7c1e4b2a-9d3f-4e8a-b6c5-2f0a1d9e3b47',
		displayOptions: { show: { ...showForPost, operation: ['get', 'delete', 'retry', 'update'] } },
	},
	{
		displayName: 'Only One Channel',
		name: 'targetId',
		type: 'string',
		default: '',
		placeholder: 'e.g. 5b1e…',
		displayOptions: { show: { ...showForPost, operation: ['retry'] } },
		description: 'A target ID from the post. Leave empty to retry every channel that failed.',
	},

	// ----------------------------------
	//     post:update
	// ----------------------------------
	{
		displayName: 'Update Fields',
		name: 'updateFields',
		type: 'collection',
		placeholder: 'Add Field',
		default: {},
		displayOptions: { show: { ...showForPost, operation: ['update'] } },
		options: [
			{
				displayName: 'Alt Texts',
				name: 'altTexts',
				type: 'string',
				typeOptions: { rows: 3 },
				default: '',
				description: 'One line per file, in the same order as the media IDs',
			},
			{
				displayName: 'Channel Names or IDs',
				name: 'channels',
				type: 'multiOptions',
				typeOptions: { loadOptionsMethod: 'getChannels' },
				default: [],
				description: 'Replaces the channel list. Only before any channel has started going out. Choose from the list, or specify values using an <a href="https://docs.n8n.io/code/expressions/">expression</a>. Choose from the list, or specify IDs using an <a href="https://docs.n8n.io/code/expressions/">expression</a>.',
			},
			{
				displayName: 'Keep Approval',
				name: 'keepApproval',
				type: 'boolean',
				default: false,
				description: 'Whether a small fix keeps a client’s approval instead of asking them again',
			},
			{
				displayName: 'Link URL',
				name: 'linkUrl',
				type: 'string',
				default: '',
			},
			{
				displayName: 'Local Time',
				name: 'scheduledLocal',
				type: 'string',
				default: '',
				placeholder: 'e.g. 2026-11-02T09:30',
				description: 'Send a draft out at this wall-clock time in each channel’s zone',
			},
			{
				displayName: 'Media IDs',
				name: 'mediaIds',
				type: 'string',
				default: '',
				description: 'Comma-separated; replaces the files the post had',
			},
			{
				displayName: 'Scheduled At',
				name: 'scheduledAt',
				type: 'dateTime',
				default: '',
				description: 'A new time. Giving a draft a time schedules it (needs posts:publish).',
			},
			{
				displayName: 'Send Draft to Queue',
				name: 'queue',
				type: 'boolean',
				default: false,
				description: 'Whether to send a draft into the queue, each channel taking its next free slot',
			},
			{
				displayName: 'Text',
				name: 'content',
				type: 'string',
				typeOptions: { rows: 5 },
				default: '',
			},
		],
	},
	{
		...networkOptions,
		description: 'Applied only when the channel list is replaced in the update fields',
		displayOptions: { show: { ...showForPost, operation: ['update'] } },
	},

	// ----------------------------------
	//     post:getAll
	// ----------------------------------
	{
		displayName: 'Return All',
		name: 'returnAll',
		type: 'boolean',
		default: false,
		displayOptions: { show: { ...showForPost, operation: ['getAll'] } },
		description: 'Whether to return all results or only up to a given limit',
	},
	{
		displayName: 'Limit',
		name: 'limit',
		type: 'number',
		typeOptions: { minValue: 1 },
		default: 50,
		displayOptions: { show: { ...showForPost, operation: ['getAll'], returnAll: [false] } },
		description: 'Max number of results to return',
	},
	{
		displayName: 'Filters',
		name: 'filters',
		type: 'collection',
		placeholder: 'Add Filter',
		default: {},
		displayOptions: { show: { ...showForPost, operation: ['getAll'] } },
		options: [
			{
				displayName: 'Days Back',
				name: 'days',
				type: 'number',
				typeOptions: { minValue: 1, maxValue: 730 },
				default: 120,
				description: 'Without a date range: how far back to look. Upcoming posts are always included.',
			},
			{
				displayName: 'From',
				name: 'from',
				type: 'dateTime',
				default: '',
				description: 'With To: only posts that went out, or are due, in this range',
			},
			{
				displayName: 'Status',
				name: 'status',
				type: 'options',
				default: 'scheduled',
				options: [
					{ name: 'Canceled', value: 'canceled' },
					{ name: 'Done', value: 'done' },
					{ name: 'Draft', value: 'draft' },
					{ name: 'Publishing', value: 'publishing' },
					{ name: 'Scheduled', value: 'scheduled' },
				],
			},
			{
				displayName: 'To',
				name: 'to',
				type: 'dateTime',
				default: '',
			},
		],
	},
];
