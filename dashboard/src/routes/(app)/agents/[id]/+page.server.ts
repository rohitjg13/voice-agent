import { fail } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { Agent } from '$lib/types';
import { buildConfigFromForm } from '$lib/server/pack-form';
import type { Actions, PageServerLoad } from './$types';

type Source = { source: string; chunks: number };

export const load: PageServerLoad = async (event) => {
	const [agent, knowledge] = await Promise.all([
		apiJson<Agent>(event, `/api/v1/agents/${event.params.id}`),
		apiJson<Source[]>(event, `/api/v1/agents/${event.params.id}/knowledge`)
	]);
	return { agent, knowledge };
};

export const actions: Actions = {
	save: async (event) => {
		const form = await event.request.formData();
		const current = await apiJson<Agent>(event, `/api/v1/agents/${event.params.id}`);
		const config = buildConfigFromForm(form, current.config);

		const res = await api(event, `/api/v1/agents/${event.params.id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(config)
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { saved: true };
	},

	upload: async (event) => {
		const form = await event.request.formData();
		const file = form.get('file');
		if (!(file instanceof File) || file.size === 0) {
			return fail(400, { error: 'Pick a .md or .txt file' });
		}
		const body = new FormData();
		body.append('file', file);
		const res = await api(event, `/api/v1/agents/${event.params.id}/knowledge`, {
			method: 'POST',
			body
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { uploaded: true };
	},

	deleteSource: async (event) => {
		const form = await event.request.formData();
		const source = encodeURIComponent(String(form.get('source') ?? ''));
		const res = await api(event, `/api/v1/agents/${event.params.id}/knowledge/${source}`, {
			method: 'DELETE'
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { deleted: true };
	},

	publish: async (event) => {
		const res = await api(event, `/api/v1/agents/${event.params.id}/publish`, {
			method: 'POST'
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { published: true };
	}
};
