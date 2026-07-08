import { fail } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { Actions, PageServerLoad } from './$types';

type Lead = {
	id: string;
	name: string | null;
	company: string | null;
	phone_e164: string;
	status: string;
	attempts: number;
	last_error: string | null;
	vapi_call_id: string | null;
};
type CampaignDetail = {
	id: string;
	name: string;
	status: string;
	agent_id: string;
	phone_number_id: string | null;
	total_leads: number;
	done_leads: number;
	calling_leads: number;
	leads: Lead[];
};

export const load: PageServerLoad = async (event) => {
	return {
		campaign: await apiJson<CampaignDetail>(event, `/api/v1/campaigns/${event.params.id}`)
	};
};

export const actions: Actions = {
	upload: async (event) => {
		const form = await event.request.formData();
		const file = form.get('file');
		if (!(file instanceof File) || file.size === 0) {
			return fail(400, { error: 'Pick a CSV file' });
		}
		const body = new FormData();
		body.append('file', file);
		const res = await api(event, `/api/v1/campaigns/${event.params.id}/leads`, {
			method: 'POST',
			body
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { report: await res.json() };
	},

	start: async (event) => {
		const res = await api(event, `/api/v1/campaigns/${event.params.id}/start`, {
			method: 'POST'
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { started: true };
	},

	pause: async (event) => {
		const res = await api(event, `/api/v1/campaigns/${event.params.id}/pause`, {
			method: 'POST'
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { paused: true };
	}
};
