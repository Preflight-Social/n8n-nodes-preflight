import type { INodeProperties } from 'n8n-workflow';

const showForChannel = { resource: ['channel'] };

export const channelOperations: INodeProperties[] = [
	{
		displayName: 'Operation',
		name: 'operation',
		type: 'options',
		noDataExpression: true,
		displayOptions: { show: showForChannel },
		options: [
			{
				name: 'Get Many',
				value: 'getAll',
				description: 'List the social accounts connected to the workspace',
				action: 'Get many channels',
			},
			{
				name: 'Get Next Queue Times',
				value: 'getNextQueueTimes',
				description: 'When the queue would next post to each channel, from its posting schedule',
				action: 'Get next queue times for channels',
			},
		],
		default: 'getAll',
	},
];

export const channelFields: INodeProperties[] = [
	{
		displayName: 'Return All',
		name: 'returnAll',
		type: 'boolean',
		default: false,
		displayOptions: { show: { ...showForChannel, operation: ['getAll'] } },
		description: 'Whether to return all results or only up to a given limit',
	},
	{
		displayName: 'Limit',
		name: 'limit',
		type: 'number',
		typeOptions: { minValue: 1 },
		default: 50,
		displayOptions: { show: { ...showForChannel, operation: ['getAll'], returnAll: [false] } },
		description: 'Max number of results to return',
	},
	{
		displayName: 'Filters',
		name: 'filters',
		type: 'collection',
		placeholder: 'Add Filter',
		default: {},
		displayOptions: { show: { ...showForChannel, operation: ['getAll'] } },
		options: [
			{
				displayName: 'Network',
				name: 'platform',
				type: 'options',
				default: 'bluesky',
				options: [
					{ name: 'Bluesky', value: 'bluesky' },
					{ name: 'Discord', value: 'discord' },
					{ name: 'Facebook', value: 'facebook' },
					{ name: 'Instagram', value: 'instagram' },
					{ name: 'LinkedIn', value: 'linkedin' },
					{ name: 'Mastodon', value: 'mastodon' },
					{ name: 'Pinterest', value: 'pinterest' },
					{ name: 'Telegram', value: 'telegram' },
					{ name: 'Threads', value: 'threads' },
					{ name: 'TikTok', value: 'tiktok' },
					{ name: 'Tumblr', value: 'tumblr' },
					{ name: 'YouTube', value: 'youtube' },
				],
				description: 'Only channels on this network',
			},
			{
				displayName: 'Usable Only',
				name: 'usableOnly',
				type: 'boolean',
				default: true,
				description: 'Whether to leave out channels that need reconnecting or are paused by the plan',
			},
		],
	},
	{
		displayName: 'Channel Names or IDs',
		name: 'channelIds',
		type: 'multiOptions',
		typeOptions: { loadOptionsMethod: 'getChannelIds' },
		default: [],
		displayOptions: { show: { ...showForChannel, operation: ['getNextQueueTimes'] } },
		description:
			'Channels to ask about. Leave empty for every connected channel. Choose from the list, or specify IDs using an <a href="https://docs.n8n.io/code/expressions/">expression</a>.',
	},
];
