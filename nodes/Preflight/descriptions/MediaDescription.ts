import type { INodeProperties } from 'n8n-workflow';

const showForMedia = { resource: ['media'] };

export const mediaOperations: INodeProperties[] = [
	{
		displayName: 'Operation',
		name: 'operation',
		type: 'options',
		noDataExpression: true,
		displayOptions: { show: showForMedia },
		options: [
			{
				name: 'Delete',
				value: 'delete',
				description: 'Delete a file from the media library',
				action: 'Delete a media file',
			},
			{
				name: 'Get',
				value: 'get',
				description: 'Get a file’s status, facts and a short-lived preview link',
				action: 'Get a media file',
			},
			{
				name: 'Upload',
				value: 'upload',
				description: 'Add an image or video from a public URL or from binary data',
				action: 'Upload a media file',
			},
		],
		default: 'upload',
	},
];

export const mediaFields: INodeProperties[] = [
	// ----------------------------------
	//         media:upload
	// ----------------------------------
	{
		displayName: 'Source',
		name: 'source',
		type: 'options',
		noDataExpression: true,
		default: 'url',
		displayOptions: { show: { ...showForMedia, operation: ['upload'] } },
		options: [
			{
				name: 'Public URL',
				value: 'url',
				description: 'Preflight downloads the file itself; nothing passes through n8n',
			},
			{
				name: 'Binary File',
				value: 'binary',
				description: 'A file from a previous node, uploaded straight to Preflight’s storage',
			},
		],
	},
	{
		displayName: 'File URL',
		name: 'sourceUrl',
		type: 'string',
		required: true,
		default: '',
		placeholder: 'e.g. https://example.com/video.mp4',
		displayOptions: { show: { ...showForMedia, operation: ['upload'], source: ['url'] } },
		description: 'A public https address Preflight can download',
	},
	{
		displayName: 'Input Binary Field',
		name: 'binaryPropertyName',
		type: 'string',
		required: true,
		default: 'data',
		displayOptions: { show: { ...showForMedia, operation: ['upload'], source: ['binary'] } },
		hint: 'The name of the input binary field containing the file to upload',
	},
	{
		displayName: 'Kind',
		name: 'kind',
		type: 'options',
		default: 'auto',
		displayOptions: { show: { ...showForMedia, operation: ['upload'] } },
		options: [
			{ name: 'Detect From File', value: 'auto' },
			{ name: 'Image', value: 'image' },
			{ name: 'Video', value: 'video' },
		],
		description: 'Whether the file is an image or a video. Detected from the MIME type or the extension when possible.',
	},
	{
		displayName: 'Wait Until Ready',
		name: 'waitUntilReady',
		type: 'boolean',
		default: true,
		displayOptions: { show: { ...showForMedia, operation: ['upload'] } },
		description:
			'Whether to wait until Preflight has the file and has measured it. A post can only use a file that is ready.',
	},
	{
		displayName: 'Options',
		name: 'options',
		type: 'collection',
		placeholder: 'Add Option',
		default: {},
		displayOptions: { show: { ...showForMedia, operation: ['upload'] } },
		options: [
			{
				displayName: 'Duration (Seconds)',
				name: 'durationSeconds',
				type: 'number',
				typeOptions: { minValue: 0, numberPrecision: 2 },
				default: 0,
				description: 'Video length, if known. Preflight measures it too.',
			},
			{
				displayName: 'File Name',
				name: 'fileName',
				type: 'string',
				default: '',
				placeholder: 'e.g. launch-teaser.mp4',
			},
			{
				displayName: 'Height (Px)',
				name: 'height',
				type: 'number',
				typeOptions: { minValue: 0 },
				default: 0,
			},
			{
				displayName: 'MIME Type',
				name: 'mimeType',
				type: 'string',
				default: '',
				placeholder: 'e.g. video/mp4',
				description: 'Overrides the type taken from the binary data or the URL',
			},
			{
				displayName: 'Wait Timeout (Seconds)',
				name: 'waitTimeout',
				type: 'number',
				typeOptions: { minValue: 10 },
				default: 600,
				description: 'How long to wait for the file to become ready before stopping with a message',
			},
			{
				displayName: 'Width (Px)',
				name: 'width',
				type: 'number',
				typeOptions: { minValue: 0 },
				default: 0,
			},
		],
	},

	// ----------------------------------
	//         media:get / delete
	// ----------------------------------
	{
		displayName: 'Media ID',
		name: 'mediaId',
		type: 'string',
		required: true,
		default: '',
		placeholder: 'e.g. 1f0c2b7e-5d1a-4a7b-9a63-2a1f7c9e8b41',
		displayOptions: { show: { ...showForMedia, operation: ['get', 'delete'] } },
	},
];
