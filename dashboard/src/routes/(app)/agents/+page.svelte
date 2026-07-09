<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
	let creating = $state(false);
</script>

<svelte:head><title>Agents — Coldline</title></svelte:head>

<div class="flex items-center justify-between">
	<div>
		<h1 class="text-2xl font-bold tracking-tight">Agents</h1>
		<p class="mt-1 text-sm text-muted">Each agent is a configurable industry pack with its own voice, scripts and knowledge.</p>
	</div>
	<button class="btn" onclick={() => (creating = !creating)}>+ New agent</button>
</div>

{#if form?.error}
	<div class="flash-danger mt-4">{form.error}</div>
{/if}

{#if creating}
	<form method="POST" action="?/create" use:enhance class="card mt-6 flex flex-wrap items-end gap-4 p-5">
		<div class="grow">
			<label class="label" for="name">Agent name</label>
			<input class="input" id="name" name="name" required placeholder="Midwest outbound" />
		</div>
		<div>
			<label class="label" for="template_name">Industry pack</label>
			<select class="input" id="template_name" name="template_name" required>
				<optgroup label="Built-in packs">
					{#each data.templates as t (t.name)}
						<option value={t.name}>{t.industry} — {t.product_name}</option>
					{/each}
				</optgroup>
				{#if data.packs.length > 0}
					<optgroup label="Your packs">
						{#each data.packs as p (p.name)}
							<option value={p.name}>{p.industry} — {p.product_name}</option>
						{/each}
					</optgroup>
				{/if}
			</select>
		</div>
		<button class="btn" type="submit">Create</button>
	</form>
{/if}

<div class="mt-6 grid gap-4 lg:grid-cols-2">
	{#each data.agents as a (a.id)}
		<a href="/agents/{a.id}" class="card group p-5 transition-all duration-200"
			style="hover:shadow-[6px_6px_18px_hsl(222_13%_5%/0.8),_-4px_-4px_12px_hsl(222_13%_15%/0.4)]"
		>
			<div class="flex items-center justify-between">
				<span class="text-lg font-semibold group-hover:text-phos">{a.name}</span>
				<span class="font-mono text-[11px] uppercase tracking-widest
					{a.status === 'active' ? 'text-phos' : a.status === 'archived' ? 'text-muted' : 'text-amber'}">
					{#if a.status === 'active'}<span class="pulse-dot mr-1.5"></span>{/if}{a.status}
				</span>
			</div>
			<div class="mt-2 font-mono text-[12px] text-muted">
				pack: {a.template_name ?? 'custom'}
				{#if a.vapi_assistant_id}· published{/if}
			</div>
		</a>
	{:else}
		<div class="card p-8 text-center text-sm text-muted lg:col-span-2">
			No agents yet — create one from an industry pack.
		</div>
	{/each}
</div>
