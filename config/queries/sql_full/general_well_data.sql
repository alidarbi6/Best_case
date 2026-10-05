-- General well data: job LEFT JOIN rig LEFT JOIN well header (specification v2)
SELECT
  j."idwell",
  w."wellname",
  j."idrec",
  j."dttmend",
  j."dttmspud",
  j."dttmstart",
  j."jobtyp",
  r."contractor",
  r."dttmend" AS "dttmend (Right)",
  r."dttmstart" AS "dttmstart (Right)",
  r."rigno"
FROM
  dbo.wvt_wvjob j
LEFT JOIN
  dbo.wvt_wvjobrig r
ON
  j."idrec" = r."idrecparent"
LEFT JOIN
  dbo.wvt_wvwellheader w
ON
  j."idwell" = w."idwell";
