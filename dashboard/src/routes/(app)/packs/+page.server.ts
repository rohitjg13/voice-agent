import { apiJson } from '$lib/server/api';
import type { PackSummary } from '$lib/types';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async (event) => {
	const [templates, packs] = await Promise.all([
		apiJson<PackSummary[]>(event, '/api/v1/templates'),
		apiJson<PackSummary[]>(event, '/api/v1/packs')
	]);
	return { templates, packs };
};
