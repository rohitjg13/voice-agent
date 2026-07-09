<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';

	let { data, form } = $props();

	const a = $derived(data.agent);
	const c = $derived(data.agent.config);

	const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
	const objRows = $derived([
		...c.objections,
		{ id: '', label: '', patterns: [], responses: [], max_strikes: 3 }
	]);
</script>

<svelte:head><title>{a.name} — Coldline</title></svelte:head>

<div class="flex flex-wrap items-center justify-between gap-4">
	<div>
		<a class="font-mono text-[12px] text-muted hover:text-phos transition-colors" href="/agents">← agents</a>
		<h1 class="mt-1 text-2xl font-bold tracking-tight">{a.name}</h1>
		<div class="mt-1 font-mono text-[12px] text-muted">
			pack: {a.template_name ?? 'custom'} ·
			<span class={a.status === 'active' ? 'text-phos' : 'text-amber'}>{a.status}</span>
			{#if a.vapi_assistant_id}· assistant {a.vapi_assistant_id.slice(0, 8)}…{/if}
		</div>
	</div>
	<form method="POST" action="?/publish" use:enhance={() => async ({ update }) => { await update(); await invalidateAll(); }}>
		<button class="btn" type="submit">
			{a.vapi_assistant_id ? 'Republish to Vapi' : 'Publish to Vapi'}
		</button>
	</form>
</div>

{#if form?.error}
	<div class="flash-danger mt-4">{form.error}</div>
{:else if form?.saved}
	<div class="flash-success mt-4">Saved.</div>
{:else if form?.published}
	<div class="flash-success mt-4">Published to Vapi.</div>
{/if}

<form method="POST" action="?/save" use:enhance class="mt-6 space-y-6">
	<section class="card p-6">
		<h2 class="section-h">01 / persona &amp; product</h2>
		<div class="grid gap-4 sm:grid-cols-2">
			<div>
				<label class="label" for="agent_name">Agent persona name</label>
				<input class="input" id="agent_name" name="agent_name" value={c.agent.name} />
			</div>
			<div>
				<label class="label" for="voice_id">ElevenLabs voice ID</label>
				<input class="input font-mono" id="voice_id" name="voice_id" value={c.agent.voice_id} />
			</div>
			<div>
				<label class="label" for="product_name">Product name</label>
				<input class="input" id="product_name" name="product_name" value={c.product.name} />
			</div>
			<div class="sm:col-span-2">
				<label class="label" for="product_description">Product description</label>
				<textarea class="input" id="product_description" name="product_description" rows="2">{c.product.description}</textarea>
			</div>
			<div class="sm:col-span-2">
				<label class="label" for="key_benefits">Key benefits (one per line)</label>
				<textarea class="input font-mono text-[13px]" id="key_benefits" name="key_benefits" rows="3">{c.product.key_benefits.join('\n')}</textarea>
			</div>
		</div>
	</section>

	<section class="card p-6">
		<h2 class="section-h">02 / call scripts</h2>
		<div class="grid gap-4">
			<div>
				<label class="label" for="system_prompt_template">System prompt template (Jinja2)</label>
				<textarea class="input font-mono text-[13px]" id="system_prompt_template" name="system_prompt_template" rows="8">{c.system_prompt_template}</textarea>
			</div>
			<div class="grid gap-4 sm:grid-cols-2">
				<div>
					<label class="label" for="opener">Opener</label>
					<textarea class="input" id="opener" name="opener" rows="3">{c.stages.opener}</textarea>
				</div>
				<div>
					<label class="label" for="permission">Permission ask</label>
					<textarea class="input" id="permission" name="permission" rows="3">{c.stages.permission}</textarea>
				</div>
				<div>
					<label class="label" for="discovery_questions">Discovery questions (one per line)</label>
					<textarea class="input" id="discovery_questions" name="discovery_questions" rows="4">{c.stages.discovery_questions.join('\n')}</textarea>
				</div>
				<div>
					<label class="label" for="pitch_points">Pitch points (one per line)</label>
					<textarea class="input" id="pitch_points" name="pitch_points" rows="4">{c.stages.pitch_points.join('\n')}</textarea>
				</div>
				<div>
					<label class="label" for="close">Close</label>
					<textarea class="input" id="close" name="close" rows="3">{c.stages.close}</textarea>
				</div>
				<div>
					<label class="label" for="schedule">Scheduling script</label>
					<textarea class="input" id="schedule" name="schedule" rows="3">{c.stages.schedule}</textarea>
				</div>
			</div>
		</div>
	</section>

	<section class="card p-6">
		<h2 class="section-h mb-1">03 / objection playbook</h2>
		<p class="mb-4 text-sm text-muted">Escalating responses — one per strike. Blank label = row ignored.</p>
		<div class="space-y-4">
			{#each objRows as obj, i (i)}
				<div class="objection-row">
					<input type="hidden" name="obj_{i}_id" value={obj.id} />
					<div class="grid gap-3 sm:grid-cols-[2fr_3fr_90px_70px]">
						<div>
							<label class="label" for="obj_{i}_label">Label</label>
							<input class="input" id="obj_{i}_label" name="obj_{i}_label" value={obj.label} placeholder="Too expensive" />
						</div>
						<div>
							<label class="label" for="obj_{i}_patterns">Trigger phrases (comma-separated)</label>
							<input class="input font-mono text-[13px]" id="obj_{i}_patterns" name="obj_{i}_patterns" value={obj.patterns.join(', ')} />
						</div>
						<div>
							<label class="label" for="obj_{i}_max_strikes">Strikes</label>
							<input class="input font-mono" id="obj_{i}_max_strikes" name="obj_{i}_max_strikes" type="number" min="1" max="5" value={obj.max_strikes} />
						</div>
						{#if obj.id}
							<div class="flex items-end pb-2">
								<label class="flex items-center gap-1.5 font-mono text-[11px] text-danger">
									<input type="checkbox" name="obj_{i}_delete" /> drop
								</label>
							</div>
						{/if}
					</div>
					<div class="mt-3">
						<label class="label" for="obj_{i}_responses">Responses, escalating (one per line)</label>
						<textarea class="input text-[13px]" id="obj_{i}_responses" name="obj_{i}_responses" rows="3">{obj.responses.join('\n')}</textarea>
					</div>
				</div>
			{/each}
		</div>
	</section>

	<section class="card p-6">
		<h2 class="section-h">04 / compliance &amp; scheduling</h2>
		<div class="grid gap-4 sm:grid-cols-2">
			<div>
				<label class="label" for="never_say">Never say (one per line)</label>
				<textarea class="input font-mono text-[13px]" id="never_say" name="never_say" rows="4">{c.compliance.never_say.join('\n')}</textarea>
			</div>
			<div>
				<label class="label" for="required_disclosure">Required disclosure</label>
				<textarea class="input" id="required_disclosure" name="required_disclosure" rows="4">{c.compliance.required_disclosure}</textarea>
				<label class="mt-3 flex items-center gap-2 text-sm text-muted">
					<input type="checkbox" name="do_not_call_check" checked={c.compliance.do_not_call_check} />
					Check do-not-call list before dialing
				</label>
			</div>
			<div>
				<span class="label">Working days</span>
				<div class="flex flex-wrap gap-2">
					{#each DAYS as day (day)}
						<label class="day-chip">
							<input class="sr-only" type="checkbox" name="working_days" value={day}
								checked={c.scheduling.working_days.includes(day)} />
							{day.slice(0, 3)}
						</label>
					{/each}
				</div>
			</div>
			<div class="grid gap-4 sm:grid-cols-2">
				<div>
					<label class="label" for="working_hours">Working hours</label>
					<input class="input" id="working_hours" name="working_hours" value={c.scheduling.working_hours} />
				</div>
				<div>
					<label class="label" for="timezone">Timezone</label>
					<input class="input font-mono text-[13px]" id="timezone" name="timezone" value={c.scheduling.timezone} />
				</div>
			</div>
		</div>
	</section>

	<div class="sticky-bar">
		<button class="btn" type="submit">Save configuration</button>
	</div>
</form>

<section class="card mt-6 p-6">
	<h2 class="section-h mb-1">05 / knowledge base</h2>
	<p class="mb-4 text-sm text-muted">
		Markdown or text files, chunked and embedded — grounds objection handling for this agent.
	</p>
	<form method="POST" action="?/upload" use:enhance enctype="multipart/form-data" class="flex items-center gap-3">
		<input class="input max-w-xs" type="file" name="file" accept=".md,.txt" required />
		<button class="btn-ghost" type="submit">Upload</button>
	</form>
	<ul class="mt-4 space-y-1">
		{#each data.knowledge as k (k.source)}
			<li class="flex items-center justify-between py-2.5 sep-y">
				<span class="font-mono text-sm">{k.source}</span>
				<div class="flex items-center gap-4">
					<span class="font-mono text-[12px] text-muted">{k.chunks} chunks</span>
					<form method="POST" action="?/deleteSource" use:enhance>
						<input type="hidden" name="source" value={k.source} />
						<button class="btn-danger" type="submit">remove</button>
					</form>
				</div>
			</li>
		{:else}
			<li class="py-3 text-sm text-muted">No documents uploaded yet.</li>
		{/each}
	</ul>
</section>
