<script lang="ts">
	import { enhance } from '$app/forms';

	let { form } = $props();
</script>

<svelte:head><title>Sign in — Coldline</title></svelte:head>

<form method="POST" use:enhance class="card space-y-4 p-6">
	{#if form?.error}
		<p class="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
			{form.error}
		</p>
	{/if}
	<div>
		<label class="label" for="email">Email</label>
		<input class="input" id="email" name="email" type="email" value={form?.email ?? ''} required />
	</div>
	<div>
		<label class="label" for="password">Password</label>
		<input class="input" id="password" name="password" type="password" required />
	</div>
	<button class="btn w-full justify-center" type="submit">Sign in</button>
	<p class="text-center text-sm text-muted">
		No account? <a class="text-phos hover:underline" href="/signup">Create one</a>
	</p>
</form>
