<script lang="ts">
	import { enhance } from '$app/forms';

	let { form } = $props();
</script>

<svelte:head><title>Sign up — Coldline</title></svelte:head>

{#if form?.confirm}
	<div class="card p-6 text-center">
		<p class="text-sm">
			Check <span class="font-mono text-phos">{form.email}</span> for a confirmation link.
		</p>
	</div>
{:else}
	<form method="POST" use:enhance class="card space-y-4 p-6">
		{#if form?.error}
			<div class="flash-danger">{form.error}</div>
		{/if}
		<div>
			<label class="label" for="full_name">Your name</label>
			<input class="input" id="full_name" name="full_name" type="text" />
		</div>
		<div>
			<label class="label" for="email">Email</label>
			<input class="input" id="email" name="email" type="email" value={form?.email ?? ''} required />
		</div>
		<div>
			<label class="label" for="password">Password</label>
			<input class="input" id="password" name="password" type="password" minlength="8" required />
		</div>
		<button class="btn w-full justify-center" type="submit">Create account</button>
		<p class="text-center text-sm text-muted">
			Already registered? <a class="text-phos hover:underline" href="/login">Sign in</a>
		</p>
	</form>
{/if}
