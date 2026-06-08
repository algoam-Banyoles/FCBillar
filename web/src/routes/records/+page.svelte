<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';

	type Rec = { categoria: string; ordre: number; player_fcb_id: string | null; jugador: string; valor: string };
	let recs = $state<Rec[]>([]);
	let loading = $state(true);

	onMount(async () => {
		const { data } = await supabase
			.from('records')
			.select('categoria, ordre, player_fcb_id, jugador, valor')
			.order('categoria')
			.order('ordre');
		recs = (data ?? []) as Rec[];
		loading = false;
	});

	const cats = $derived([...new Set(recs.map((r) => r.categoria))]);
</script>

<h1 class="mb-3 text-lg font-bold">Rècords</h1>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else}
	<div class="space-y-4 lg:grid lg:grid-cols-2 lg:gap-4 lg:space-y-0">
		{#each cats as cat}
			<div class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
				<div class="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
					{cat}
				</div>
				<ul>
					{#each recs.filter((r) => r.categoria === cat) as r (r.ordre)}
						<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
							<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums {r.ordre === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.ordre}</span>
							{#if r.player_fcb_id}
								<a href="/jugador/{r.player_fcb_id}" class="min-w-0 flex-1 truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
							{:else}
								<span class="min-w-0 flex-1 truncate text-sm">{r.jugador}</span>
							{/if}
							<span class="shrink-0 font-mono text-sm font-bold tabular-nums">{r.valor}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/each}
	</div>
{/if}
