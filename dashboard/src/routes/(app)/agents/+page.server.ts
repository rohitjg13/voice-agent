import { fail, redirect } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { PackSummary } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

type Agent = {
	id: string;
	name: string;
	template_name: string | null;
	status: string;
	vapi_assistant_id: string | null;
};
type Template = { name: string; industry: string; agent_name: string; product_name: string };

export const load: PageServerLoad = async (event) => {
	const [agents, templates, packs] = await Promise.all([
		apiJson<Agent[]>(event, '/api/v1/agents'),
		apiJson<Template[]>(event, '/api/v1/templates'),
		apiJson<PackSummary[]>(event, '/api/v1/packs')
	]);
	return { agents, templates, packs };
};

export const actions: Actions = {
	create: async (event) => {
		const form = await event.request.formData();
		const res = await api(event, '/api/v1/agents', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				name: String(form.get('name') ?? '').trim(),
				template_name: String(form.get('template_name') ?? '')
			})
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		const agent = await res.json();
		redirect(303, `/agents/${agent.id}`);
	}
};
