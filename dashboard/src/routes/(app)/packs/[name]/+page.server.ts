import { fail, redirect } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { PackConfig } from '$lib/types';
import { buildConfigFromForm } from '$lib/server/pack-form';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async (event) => {
	const pack = await apiJson<PackConfig>(event, `/api/v1/packs/${event.params.name}`);
	return { pack };
};

export const actions: Actions = {
	save: async (event) => {
		const form = await event.request.formData();
		const current = await apiJson<PackConfig>(event, `/api/v1/packs/${event.params.name}`);
		const config = buildConfigFromForm(form, current);

		const res = await api(event, `/api/v1/packs/${event.params.name}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(config)
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { saved: true };
	},

	delete: async (event) => {
		const res = await api(event, `/api/v1/packs/${event.params.name}`, {
			method: 'DELETE'
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		redirect(303, '/packs');
	}
};
