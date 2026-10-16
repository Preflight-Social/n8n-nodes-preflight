import type {
	IAuthenticateGeneric,
	Icon,
	ICredentialTestRequest,
	ICredentialType,
	INodeProperties,
} from 'n8n-workflow';

export class PreflightApi implements ICredentialType {
	name = 'preflightApi';

	displayName = 'Preflight API';

	icon: Icon = { light: 'file:../icons/preflight.svg', dark: 'file:../icons/preflight.dark.svg' };

	documentationUrl = 'https://github.com/Preflight-Social/n8n-nodes-preflight#credentials';

	properties: INodeProperties[] = [
		{
			displayName: 'API Key',
			name: 'apiKey',
			type: 'string',
			typeOptions: { password: true },
			required: true,
			default: '',
			placeholder: 'e.g. sk_live_...',
			description:
				'Create one in Preflight under Settings → API keys. Give it the scopes your workflows need: posts:read, posts:write (drafts), posts:publish (anything that goes live), media:read, media:write, webhooks:read and webhooks:write (for the trigger).',
		},
		{
			displayName: 'Base URL',
			name: 'baseUrl',
			type: 'string',
			default: 'https://preflight.social',
			placeholder: 'e.g. https://preflight.social',
			description: 'Only change this for a self-hosted or staging Preflight. Without the /v1 path.',
		},
	];

	authenticate: IAuthenticateGeneric = {
		type: 'generic',
		properties: {
			headers: {
				Authorization: '=Bearer {{$credentials.apiKey}}',
			},
		},
	};

	test: ICredentialTestRequest = {
		request: {
			baseURL: '={{$credentials.baseUrl.replace(/\\/+$/, "")}}/v1',
			url: '/oauth/accounts',
			method: 'GET',
		},
	};
}
