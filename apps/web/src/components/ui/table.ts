/**
 * A list that is a table from 768 px and a stack of cards below it (M6-P2, decision 2A), from
 * one markup: put `TABLE` on the `<table>`, give every `<td>` a `data-label` naming its column
 * (an empty one for the cell that needs no name, such as the actions), and keep the explicit
 * roles so the semantics survive the phone layout's `display: block` (`globals.css`, .me-table).
 *
 *   <table className={TABLE} role="table">
 *     <thead role="rowgroup"><tr role="row"><th role="columnheader" className={TH}>…</th></tr></thead>
 *     <tbody role="rowgroup"><tr role="row" className={TR}><td role="cell" data-label="Patient" className={TD}>…</td></tr></tbody>
 *   </table>
 */
export const TABLE_WRAP = "md:overflow-x-auto md:rounded-card md:border md:border-slate-200 md:bg-white md:shadow-card";
export const TABLE = "me-table w-full border-collapse text-left";
export const TH = "border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700";
export const TR = "md:border-b md:border-slate-100 md:last:border-b-0";
export const TD = "align-top md:px-3 md:py-2.5";
