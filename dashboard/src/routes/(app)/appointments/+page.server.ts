import { apiJson } from '$lib/server/api';
import type { PageServerLoad } from './$types';

type Appointment = {
	id: string;
	call_id: string;
	booked: boolean;
	prospect_name: string | null;
	prospect_email: string | null;
	requested_time: string | null;
	summary: string | null;
	created_at: string | null;
};

export const load: PageServerLoad = async (event) => {
	return { appointments: await apiJson<Appointment[]>(event, '/api/v1/appointments') };
};
