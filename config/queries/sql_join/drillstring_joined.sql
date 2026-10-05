-- Drill string components and parameters, "Join II": drill string LEFT JOIN components
SELECT
    ds.idwell,
    ds.idrecparent,
    ds.idrec,
    ds.bitno,
    ds.bittfa,
    ds.com,
    ds.des,
    ds.stringno,
    ds.wearbearing,
    ds.weardull,
    ds.weargauge,
    ds.wearinner,
    ds.wearloc,
    ds.wearother,
    ds.wearouter,
    ds.wearpulled,
    dsc.com  AS com_DrillstringComp,
    dsc.des  AS des_DrillstringComp,
    dsc.grade,
    dsc.hoursstart,
    dsc.joints,
    dsc.length,
    dsc.make,
    dsc.model,
    dsc.sysseq
FROM
    dbo.wvt_wvjobdrillstring ds
LEFT JOIN
    dbo.wvt_wvjobdrillstringcomp dsc
    ON ds.idwell = dsc.idwell
   AND ds.idrec = dsc.idrecparent;
