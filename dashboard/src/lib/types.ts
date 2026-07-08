export type Objection = {
	id: string;
	label: string;
	patterns: string[];
	responses: string[];
	max_strikes: number;
};

export type PackConfig = {
	name: string;
	version: string;
	industry: string;
	agent: { name: string; voice_id: string };
	product: { name: string; description: string; key_benefits: string[] };
	system_prompt_template: string;
	stages: {
		opener: string;
		permission: string;
		discovery_questions: string[];
		pitch_points: string[];
		close: string;
		schedule: string;
	};
	objections: Objection[];
	compliance: { never_say: string[]; required_disclosure: string; do_not_call_check: boolean };
	scheduling: { working_days: string[]; working_hours: string; timezone: string };
};

export type Agent = {
	id: string;
	name: string;
	template_name: string | null;
	status: string;
	vapi_assistant_id: string | null;
	config: PackConfig;
};
