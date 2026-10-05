-- General well data, "Join 2": job LEFT JOIN rig
SELECT
    j.idwell,
    j.idrec,
    j.dttmend   AS job_dttmend,
    j.dttmspud,
    j.dttmstart AS job_dttmstart,
    j.jobtyp,
    r.contractor,
    r.dttmend   AS rig_dttmend,
    r.dttmstart AS rig_dttmstart,
    r.rigno
FROM
    dbo.wvt_wvjob j
LEFT JOIN
    dbo.wvt_wvjobrig r
ON
    j.idrec = r.idrecparent;
