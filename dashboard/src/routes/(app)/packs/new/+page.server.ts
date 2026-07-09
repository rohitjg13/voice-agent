import { fail, redirect } from '@sveltejs/kit';
import { api, apiJson } from '$lib/server/api';
import type { PackSummary } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async (event) => {
	const templates = await apiJson<PackSummary[]>(event, '/api/v1/templates');
	return { templates };
};

export const actions: Actions = {
	default: async (event) => {
		const form = await event.request.formData();
		const name = String(form.get('name') ?? '').trim();
		const industry = String(form.get('industry') ?? '').trim();
		const agent_name = String(form.get('agent_name') ?? '').trim();
		const product_name = String(form.get('product_name') ?? '').trim();

		if (!name || !industry || !agent_name || !product_name) {
			return fail(400, { error: 'All fields are required.' });
		}

		const res = await api(event, '/api/v1/packs', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name, industry, agent_name, product_name })
		});

		if (!res.ok) {
			const detail = await res.text();
			return fail(res.status, { error: detail });
		}

		redirect(303, `/packs/${encodeURIComponent(name)}`);
	}
};
