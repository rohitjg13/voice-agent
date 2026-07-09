<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
</script>

<svelte:head><title>Set up — Coldline</title></svelte:head>

<div class="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-4 py-12 transition-colors duration-300">
	<div class="mb-8">
		<div class="font-mono text-[11px] uppercase tracking-[0.3em] text-phos">setup / 1 of 1</div>
		<h1 class="mt-2 text-3xl font-bold tracking-tight">Set up your workspace</h1>
		<p class="mt-1 text-sm text-muted">
			Name your company and pick an industry pack — your agent starts pre-trained for it.
		</p>
	</div>

	<form method="POST" use:enhance class="card space-y-5 p-6">
		{#if form?.error}
			<div class="flash-danger">{form.error}</div>
		{/if}
		<div>
			<label class="label" for="org_name">Company name</label>
			<input class="input" id="org_name" name="org_name" required placeholder="Acme Dental Group" />
		</div>
		<div>
			<label class="label" for="agent_name">Agent name (optional)</label>
			<input class="input" id="agent_name" name="agent_name" placeholder="My first agent" />
		</div>
		<div>
			<span class="label">Industry pack</span>
			<div class="grid gap-3 sm:grid-cols-2">
				{#each data.templates as t (t.name)}
					<label
						class="card flex cursor-pointer flex-col gap-1 p-4 has-checked:shadow-[var(--shadow-inset-a),var(--shadow-inset-b)]"
					>
						<input class="sr-only" type="radio" name="template" value={t.name} />
						<span class="font-mono text-[11px] uppercase tracking-widest text-muted">{t.industry}</span>
						<span class="font-semibold">{t.product_name}</span>
						<span class="text-xs text-muted">Persona: {t.agent_name}</span>
					</label>
				{/each}
			</div>
		</div>
		<button class="btn w-full justify-center" type="submit">Create workspace</button>
	</form>
</div>
