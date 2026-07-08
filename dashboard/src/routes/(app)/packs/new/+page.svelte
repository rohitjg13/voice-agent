<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
</script>

<svelte:head><title>New Pack — Coldline</title></svelte:head>

<div class="mx-auto max-w-xl">
	<div class="mb-8">
		<a href="/packs" class="font-mono text-[13px] text-muted hover:text-phos">← Packs</a>
		<h1 class="mt-2 text-2xl font-bold tracking-tight">Create a new pack</h1>
		<p class="mt-1 text-sm text-muted">Define the industry, product, and voice for a new agent pack. You'll customize everything in the full editor after creation.</p>
	</div>

	{#if form?.error}
		<p class="mb-6 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{form.error}</p>
	{/if}

	<form method="POST" use:enhance class="card space-y-5 p-6">
		<div>
			<label class="label" for="name">Pack slug</label>
			<input class="input" id="name" name="name" required placeholder="real_estate" />
			<p class="mt-1 font-mono text-[11px] text-muted">Lowercase, no spaces. Used as the internal identifier.</p>
		</div>

		<div>
			<label class="label" for="industry">Industry</label>
			<input class="input" id="industry" name="industry" required placeholder="Real Estate" />
		</div>

		<div>
			<label class="label" for="agent_name">Agent persona name</label>
			<input class="input" id="agent_name" name="agent_name" required placeholder="Sarah" />
			<p class="mt-1 font-mono text-[11px] text-muted">The name the AI agent introduces itself with on calls.</p>
		</div>

		<div>
			<label class="label" for="product_name">Product name</label>
			<input class="input" id="product_name" name="product_name" required placeholder="PropFlow" />
		</div>

		<div class="flex items-center justify-between pt-2">
			<a href="/packs" class="btn-ghost font-mono text-[13px]">Cancel</a>
			<button class="btn" type="submit">Create pack</button>
		</div>
	</form>
</div>
