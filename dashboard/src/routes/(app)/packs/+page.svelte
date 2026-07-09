<script lang="ts">
	let { data } = $props();
</script>

<svelte:head><title>Packs — Coldline</title></svelte:head>

<div class="flex items-center justify-between">
	<div>
		<h1 class="text-2xl font-bold tracking-tight">Packs</h1>
		<p class="mt-1 text-sm text-muted">Industry packs define agent personas. Built-in packs are read-only; custom packs can be created and edited.</p>
	</div>
	<a href="/packs/new" class="btn">+ New pack</a>
</div>

{#if data.packs.length > 0}
	<div class="mt-8">
		<h2 class="font-mono text-[11px] uppercase tracking-widest text-muted">Your packs</h2>
		<div class="mt-3 grid gap-4 lg:grid-cols-2">
			{#each data.packs as p (p.name)}
				<a href="/packs/{p.name}" class="card group flex items-center justify-between p-5">
					<div class="min-w-0 flex-1">
						<div class="font-mono text-[11px] uppercase tracking-widest text-muted">{p.industry}</div>
						<div class="mt-1 text-lg font-semibold group-hover:text-phos">{p.product_name}</div>
						<div class="mt-0.5 text-xs text-muted">Persona: {p.agent_name} · v{p.version}</div>
					</div>
				</a>
			{/each}
		</div>
	</div>
{/if}

<div class="mt-8">
	<h2 class="font-mono text-[11px] uppercase tracking-widest text-muted">Built-in packs</h2>
	<div class="mt-3 grid gap-4 lg:grid-cols-2">
		{#each data.templates as t (t.name)}
			<div class="card p-5">
				<div class="flex items-center gap-2">
					<div class="font-mono text-[11px] uppercase tracking-widest text-muted">{t.industry}</div>
					<span class="pill">built-in</span>
				</div>
				<div class="mt-1 text-lg font-semibold">{t.product_name}</div>
				<div class="mt-0.5 text-xs text-muted">Persona: {t.agent_name} · v{t.version}</div>
			</div>
		{:else}
			<div class="card p-5 text-sm text-muted">No built-in packs available.</div>
		{/each}
	</div>
</div>

{#if data.packs.length === 0}
	<div class="card mt-8 p-8 text-center text-sm text-muted">
		No custom packs yet. <a href="/packs/new" class="text-phos underline">Create your first pack</a>.
	</div>
{/if}
