<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type LligaGroup, type StandingRow } from '$lib/supabase';

	let groups = $state<LligaGroup[]>([]);
	let standings = $state<StandingRow[]>([]);
	let selDiv = $state<number | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const { data: g, error: eg } = await supabase.from('lliga_groups').select('*');
			if (eg) throw eg;
			const { data: s, error: es } = await supabase
				.from('lliga_standings')
				.select('*')
				.order('posicio');
			if (es) throw es;
			groups = (g ?? []) as LligaGroup[];
			standings = (s ?? []) as StandingRow[];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const divisions = $derived.by(() => {
		const m = new Map<number, string>();
		for (const g of groups) if (!m.has(g.divisio_id)) m.set(g.divisio_id, g.divisio_nom ?? `Div ${g.divisio_id}`);
		return [...m.entries()].map(([id, nom]) => ({ id, nom })).sort((a, b) => a.id - b.id);
	});

	$effect(() => {
		if (selDiv == null && divisions.length) selDiv = divisions[0].id;
	});

	const divGroups = $derived(
		groups
			.filter((g) => g.divisio_id === selDiv)
			.sort((a, b) => {
				const fa = (a.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				const fb = (b.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				return fa - fb || (a.grup_nom ?? '').localeCompare(b.grup_nom ?? '');
			})
	);

	function rows(gid: number): StandingRow[] {
		return standings
			.filter((s) => s.divisio_id === selDiv && s.grup_id === gid)
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
</script>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if divisions.length === 0}
	<p class="py-6 text-center text-sm text-slate-400">Sense classificacions.</p>
{:else}
	<!-- Divisions: xips -->
	<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
		{#each divisions as d}
			<button
				onclick={() => (selDiv = d.id)}
				class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium {d.id === selDiv
					? 'bg-slate-900 text-white'
					: 'bg-white text-slate-600 ring-1 ring-slate-200'}">{d.nom}</button>
		{/each}
	</div>

	{#each divGroups as g (g.grup_id)}
		<section class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<header class="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
				{g.grup_nom ?? 'Grup'}
			</header>
			<div class="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
				<span class="w-5 text-center">#</span>
				<span class="flex-1">Equip</span>
				<span class="w-7 text-center">PJ</span>
				<span class="w-9 text-right">Pts</span>
			</div>
			<ul>
				{#each rows(g.grup_id) as r (r.equip)}
					<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
						<span
							class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1
								? 'text-amber-500'
								: 'text-slate-400'}">{r.posicio}</span>
						<div class="min-w-0 flex-1">
							<div class="truncate text-sm font-medium leading-tight">{r.equip}</div>
							<div class="text-[11px] tabular-nums text-slate-400">{r.g}-{r.e}-{r.p}</div>
						</div>
						<span class="w-7 shrink-0 text-center text-sm tabular-nums text-slate-500">{r.pj}</span>
						<span class="w-9 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
					</li>
				{/each}
			</ul>
		</section>
	{/each}
{/if}
