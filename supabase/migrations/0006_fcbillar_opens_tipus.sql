-- FCBillar cloud schema — afegeix el tipus de torneig a `opens`.
--
-- `tipus`: 'open' (trofeu amb nom propi) | 'campionat' (Campionat de Catalunya per
-- modalitat+divisió). Es calcula a Python (fcbillar.torneig_naming.torneig_tipus)
-- de manera coherent entre temporades, independent de si el nom porta la paraula
-- OPEN. El frontend filtra /opens i /campionats per aquest camp.

alter table fcbillar.opens add column if not exists tipus text;
