import type { Objection, PackConfig } from '$lib/types';

export const lines = (v: FormDataEntryValue | null): string[] =>
	String(v ?? '')
		.split('\n')
		.map((s) => s.trim())
		.filter(Boolean);

const slug = (s: string) =>
	s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'objection';

export function parseObjections(form: FormData): Objection[] {
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

export function buildConfigFromForm(form: FormData, current: PackConfig): PackConfig {
	return {
		...current,
		agent: {
			name: String(form.get('agent_name') ?? current.agent.name),
			voice_id: String(form.get('voice_id') ?? current.agent.voice_id)
		},
		product: {
			name: String(form.get('product_name') ?? current.product.name),
			description: String(form.get('product_description') ?? current.product.description),
			key_benefits: lines(form.get('key_benefits'))
		},
		system_prompt_template: String(form.get('system_prompt_template') ?? current.system_prompt_template),
		stages: {
			opener: String(form.get('opener') ?? current.stages.opener),
			permission: String(form.get('permission') ?? current.stages.permission),
			discovery_questions: lines(form.get('discovery_questions')),
			pitch_points: lines(form.get('pitch_points')),
			close: String(form.get('close') ?? current.stages.close),
			schedule: String(form.get('schedule') ?? current.stages.schedule)
		},
		objections: parseObjections(form),
		compliance: {
			never_say: lines(form.get('never_say')),
			required_disclosure: String(form.get('required_disclosure') ?? ''),
			do_not_call_check: form.get('do_not_call_check') === 'on'
		},
		scheduling: {
			working_days: form.getAll('working_days').map(String),
			working_hours: String(form.get('working_hours') ?? current.scheduling.working_hours),
			timezone: String(form.get('timezone') ?? current.scheduling.timezone)
		}
	};
}
