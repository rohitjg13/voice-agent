import { fail } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { Actions, PageServerLoad } from './$types';

type Plan = { id: string; name: string; price_cents: number; limits: Record<string, number> };
type Subscription = {
	plan_id: string;
	plan_name: string;
	status: string;
	limits: Record<string, number>;
	usage: Record<string, number>;
};

export const load: PageServerLoad = async (event) => {
	const [plans, subRes] = await Promise.all([
		apiJson<Plan[]>(event, '/api/v1/billing/plans'),
		api(event, '/api/v1/billing/subscription')
	]);
	const subscription = subRes.ok ? ((await subRes.json()) as Subscription) : null;
	return { plans, subscription };
};

export const actions: Actions = {
	checkout: async (event) => {
		const form = await event.request.formData();
		const res = await api(event, '/api/v1/billing/checkout', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ plan_id: String(form.get('plan_id') ?? '') })
		});
		if (!res.ok) return fail(res.status, { error: await safeDetail(res) });
		return { upgraded: true };
	}
};
