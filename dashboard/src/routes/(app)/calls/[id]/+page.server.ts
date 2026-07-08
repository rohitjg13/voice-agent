import { apiJson } from '$lib/server/api';
import type { PageServerLoad } from './$types';

type CallDetail = {
	id: string;
	vapi_call_id: string;
	customer_number: string | null;
	outcome: string | null;
	stage_reached: string | null;
	ended_reason: string | null;
	duration_seconds: number | null;
	booked: boolean;
	cost_usd: string | number | null;
	summary: string | null;
	objections: string[];
	transcript: { role: string; content: string }[] | null;
	created_at: string | null;
};

export const load: PageServerLoad = async (event) => {
	return { call: await apiJson<CallDetail>(event, `/api/v1/calls/${event.params.id}`) };
};
