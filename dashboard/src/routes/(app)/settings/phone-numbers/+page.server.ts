import { fail } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { Actions, PageServerLoad } from './$types';

type PhoneNumber = { id: string; e164: string; status: string; created_at: string | null };

export const load: PageServerLoad = async (event) => {
	return { numbers: await apiJson<PhoneNumber[]>(event, '/api/v1/phone-numbers') };
};

export const actions: Actions = {
	buy: async (event) => {
		const form = await event.request.formData();
		const areaCode = String(form.get('area_code') ?? '').trim();
		const res = await api(event, '/api/v1/phone-numbers', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ area_code: areaCode || null })
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { bought: true };
	}
};
