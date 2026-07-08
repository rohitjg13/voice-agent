import { fail } from '@sveltejs/kit';
import { api, apiJson, safeDetail } from '$lib/server/api';
import type { Agent, Objection, PackConfig } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

type Source = { source: string; chunks: number };

export const load: PageServerLoad = async (event) => {
	const [agent, knowledge] = await Promise.all([
		apiJson<Agent>(event, `/api/v1/agents/${event.params.id}`),
		apiJson<Source[]>(event, `/api/v1/agents/${event.params.id}/knowledge`)
	]);
	return { agent, knowledge };
};

const lines = (v: FormDataEntryValue | null): string[] =>
	String(v ?? '')
		.split('\n')
		.map((s) => s.trim())
		.filter(Boolean);

const slug = (s: string) =>
	s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'objection';

function parseObjections(form: FormData): Objection[] {
	const out: Objection[] = [];
	for (let i = 0; form.has(`obj_${i}_label`); i++) {
		if (form.get(`obj_${i}_delete`)) continue;
		const label = String(form.get(`obj_${i}_label`) ?? '').trim();
		if (!label) continue;
		const id = String(form.get(`obj_${i}_id`) ?? '').trim() || slug(label);
		out.push({
			id,
			label,
			patterns: String(form.get(`obj_${i}_patterns`) ?? '')
				.split(',')
				.map((s) => s.trim())
				.filter(Boolean),
			responses: lines(form.get(`obj_${i}_responses`)),
			max_strikes: Number(form.get(`obj_${i}_max_strikes`) ?? 3) || 3
		});
	}
	return out;
}

export const actions: Actions = {
	save: async (event) => {
		const form = await event.request.formData();
		// Merge form fields into the current config so unknown fields survive
		const current = await apiJson<Agent>(event, `/api/v1/agents/${event.params.id}`);
		const c: PackConfig = current.config;

		const config: PackConfig = {
			...c,
			agent: {
				name: String(form.get('agent_name') ?? c.agent.name),
				voice_id: String(form.get('voice_id') ?? c.agent.voice_id)
			},
			product: {
				name: String(form.get('product_name') ?? c.product.name),
				description: String(form.get('product_description') ?? c.product.description),
				key_benefits: lines(form.get('key_benefits'))
			},
			system_prompt_template: String(form.get('system_prompt_template') ?? c.system_prompt_template),
			stages: {
				opener: String(form.get('opener') ?? c.stages.opener),
				permission: String(form.get('permission') ?? c.stages.permission),
				discovery_questions: lines(form.get('discovery_questions')),
				pitch_points: lines(form.get('pitch_points')),
				close: String(form.get('close') ?? c.stages.close),
				schedule: String(form.get('schedule') ?? c.stages.schedule)
			},
			objections: parseObjections(form),
			compliance: {
				never_say: lines(form.get('never_say')),
				required_disclosure: String(form.get('required_disclosure') ?? ''),
				do_not_call_check: form.get('do_not_call_check') === 'on'
			},
			scheduling: {
				working_days: form.getAll('working_days').map(String),
				working_hours: String(form.get('working_hours') ?? c.scheduling.working_hours),
				timezone: String(form.get('timezone') ?? c.scheduling.timezone)
			}
		};

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
