<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
	let creating = $state(false);
</script>

<svelte:head><title>Campaigns — Coldline</title></svelte:head>

<div class="flex items-center justify-between">
	<div>
		<h1 class="text-2xl font-bold tracking-tight">Campaigns</h1>
		<p class="mt-1 text-sm text-muted">Upload a lead list, pick an agent and number, and let the dialer work.</p>
	</div>
	<button class="btn" onclick={() => (creating = !creating)}>+ New campaign</button>
</div>

{#if form?.error}
	<div class="flash-danger mt-4">{form.error}</div>
{/if}

{#if creating}
	<form method="POST" action="?/create" use:enhance class="card mt-6 flex flex-wrap items-end gap-4 p-5">
		<div class="grow">
			<label class="label" for="name">Campaign name</label>
			<input class="input" id="name" name="name" required placeholder="Q3 Chicago dentists" />
		</div>
		<div>
			<label class="label" for="agent_id">Agent</label>
			<select class="input" id="agent_id" name="agent_id" required>
				{#each data.agents as a (a.id)}
					<option value={a.id}>{a.name}{a.vapi_assistant_id ? '' : ' (unpublished)'}</option>
				{/each}
			</select>
		</div>
		<div>
			<label class="label" for="phone_number_id">From number</label>
			<select class="input" id="phone_number_id" name="phone_number_id">
				<option value="">— pick later —</option>
				{#each data.numbers as n (n.id)}
					<option value={n.id}>{n.e164}</option>
				{/each}
			</select>
		</div>
		<button class="btn" type="submit">Create</button>
	</form>
	{#if data.numbers.length === 0}
		<p class="mt-2 text-sm text-muted">
			No numbers yet — <a class="text-phos hover:underline" href="/settings/phone-numbers">provision one</a>.
		</p>
	{/if}
{/if}

<div class="mt-6 space-y-4">
	{#each data.campaigns as c (c.id)}
		{@const pct = c.total_leads ? Math.round((c.done_leads / c.total_leads) * 100) : 0}
		<a href="/campaigns/{c.id}" class="card block p-5 transition-all duration-200">
			<div class="flex items-center justify-between">
				<span class="text-lg font-semibold">{c.name}</span>
				<span class="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest
					{c.status === 'running' ? 'text-phos' : c.status === 'completed' ? 'text-muted' : 'text-amber'}">
					{#if c.status === 'running'}<span class="pulse-dot"></span>{/if}
					{c.status}
				</span>
			</div>
			<div class="mt-3 h-1.5 overflow-hidden rounded-full" style="box-shadow: var(--shadow-inset-a), var(--shadow-inset-b);">
				<div class="h-full bg-phos transition-all rounded-full" style="width: {pct}%"></div>
			</div>
			<div class="mt-2 font-mono text-[12px] text-muted">
				{c.done_leads}/{c.total_leads} leads done · {c.calling_leads} on the line
			</div>
		</a>
	{:else}
		<div class="card p-8 text-center text-sm text-muted">No campaigns yet.</div>
	{/each}
</div>
