-- District similarity graph edge list (k-NN, k=12), built by
-- scripts/build_similarity_graph.py on exogenous features only
-- (size, 5-yr enrollment growth, revenue/student, local-tax share) so
-- outcome metrics (spending) can be benchmarked against peers without
-- circularity. Rebuild + reload after each annual TEA data refresh.
CREATE TABLE IF NOT EXISTS public.district_similarity (
    district_number TEXT NOT NULL,
    peer_number     TEXT NOT NULL,
    rank            SMALLINT NOT NULL,
    distance        DOUBLE PRECISION,
    PRIMARY KEY (district_number, peer_number)
);
CREATE INDEX IF NOT EXISTS idx_similarity_district
    ON public.district_similarity (district_number, rank);

REVOKE ALL ON public.district_similarity FROM anon, authenticated;
GRANT SELECT ON public.district_similarity TO anon, authenticated;
