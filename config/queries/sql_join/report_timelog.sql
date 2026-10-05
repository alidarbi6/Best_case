-- Time log, "Join II": job report LEFT JOIN time log
SELECT
    r.idwell,
    r.idrecparent,
    r.idrec,
    r.dttmend,
    r.dttmstart,
    r.plannextrptops,
    r.rpttmactops,
    r.summaryops,
    t.code1,
    t.code2,
    t.code3,
    t.code4,
    t.com,
    t.duration,
    t.idrecwellbore,
    t.opscategory,
    t.sysseq
FROM
    dbo.wvt_wvjobreport r
LEFT JOIN
    dbo.wvt_wvjobreporttimelog t
ON
    r.idwell = t.idwell
    AND r.idrec = t.idrecparent;
