import { fail, redirect } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { Actions, PageServerLoad } from './$types';

export type CampaignRow = {
	id: string;
	name: string;
	status: string;
	agent_id: string;
	phone_number_id: string | null;
	total_leads: number;
	done_leads: number;
	calling_leads: number;
	created_at: string | null;
};
type AgentRow = { id: string; name: string; vapi_assistant_id: string | null };
type PhoneNumber = { id: string; e164: string };

export const load: PageServerLoad = async (event) => {
	const [campaigns, agents, numbers] = await Promise.all([
		apiJson<CampaignRow[]>(event, '/api/v1/campaigns'),
		apiJson<AgentRow[]>(event, '/api/v1/agents'),
		apiJson<PhoneNumber[]>(event, '/api/v1/phone-numbers')
	]);
	return { campaigns, agents, numbers };
};

export const actions: Actions = {
	create: async (event) => {
		const form = await event.request.formData();
		const phone = String(form.get('phone_number_id') ?? '');
		const res = await api(event, '/api/v1/campaigns', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				name: String(form.get('name') ?? '').trim(),
				agent_id: String(form.get('agent_id') ?? ''),
				phone_number_id: phone || null
			})
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		const campaign = await res.json();
		redirect(303, `/campaigns/${campaign.id}`);
	}
};
