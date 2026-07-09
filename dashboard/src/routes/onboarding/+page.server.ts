import { fail, redirect } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { Actions, PageServerLoad } from './$types';

type Me = { org: { id: string } | null };
type Template = { name: string; industry: string; agent_name: string; product_name: string };

export const load: PageServerLoad = async (event) => {
	if (!event.locals.session) redirect(303, '/login');
	const me = await apiJson<Me>(event, '/api/v1/me');
	if (me.org) redirect(303, '/dashboard');
	return { templates: await apiJson<Template[]>(event, '/api/v1/templates') };
};

export const actions: Actions = {
	default: async (event) => {
		const form = await event.request.formData();
		const orgName = String(form.get('org_name') ?? '').trim();
		const agentName = String(form.get('agent_name') ?? '').trim();
		const template = String(form.get('template') ?? '');
		if (!orgName) return fail(400, { error: 'Company name required' });

		const orgRes = await api(event, '/api/v1/orgs', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: orgName })
		});
		if (!orgRes.ok && orgRes.status !== 409) {
			return fail(orgRes.status, { error: await safeDetail(orgRes) });
		}

		if (template) {
			const agentRes = await api(event, '/api/v1/agents', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: agentName || `${orgName} Agent`,
					template_name: template
				})
			});
			if (!agentRes.ok) return fail(agentRes.status, { error: await safeDetail(agentRes) });
		}
		redirect(303, '/dashboard');
	}
};
