import { apiJson } from '$lib/server/api';
import type { PageServerLoad } from './$types';

type Overview = {
	total_calls: number;
	booked: number;
	book_rate: number;
	total_minutes: number;
	avg_duration_seconds: number;
	outcomes: Record<string, number>;
	top_objections: { objection: string; count: number }[];
};
type Day = { day: string; calls: number; booked: number };
type Call = {
	id: string;
	customer_number: string | null;
	outcome: string | null;
	duration_seconds: number | null;
	created_at: string | null;
};

export const load: PageServerLoad = async (event) => {
	const [overview, timeseries, recent] = await Promise.all([
		apiJson<Overview>(event, '/api/v1/analytics/overview'),
		apiJson<Day[]>(event, '/api/v1/analytics/timeseries'),
		apiJson<Call[]>(event, '/api/v1/calls?limit=8')
	]);
	return { overview, timeseries, recent };
};
