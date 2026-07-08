import { apiJson } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export type CallRow = {
	id: string;
	customer_number: string | null;
	direction: string;
	outcome: string | null;
	stage_reached: string | null;
	duration_seconds: number | null;
	booked: boolean;
	summary: string | null;
	created_at: string | null;
};

export const load: PageServerLoad = async (event) => {
	const outcome = event.url.searchParams.get('outcome');
	const qs = outcome ? `&outcome=${encodeURIComponent(outcome)}` : '';
	return {
		calls: await apiJson<CallRow[]>(event, `/api/v1/calls?limit=100${qs}`),
		outcome
	};
};
