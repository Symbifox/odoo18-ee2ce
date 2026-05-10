--
-- PostgreSQL database dump (synthetic, for unit tests)
--

SET statement_timeout = 0;

CREATE TABLE public.res_partner (
    id integer NOT NULL,
    name character varying NOT NULL,
    email character varying,
    enterprise_only_field character varying
);

CREATE TABLE public.account_move (
    id integer NOT NULL,
    name character varying,
    state character varying
);

COPY public.res_partner (id, name, email, enterprise_only_field) FROM stdin;
1	ACME Corp	contact@acme.com	premium
2	Wile E. Coyote	wile@acme.com	standard
3	Road Runner	rr@acme.com	\N
\.

COPY public.account_move (id, name, state) FROM stdin;
100	INV/2026/0001	posted
101	INV/2026/0002	draft
\.

--
-- PostgreSQL database dump complete
--
