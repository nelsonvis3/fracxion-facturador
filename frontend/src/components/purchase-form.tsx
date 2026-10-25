"use client";
import { useCallback, useState, type FormEvent } from "react";
import { Alert, Modal, errorMessage } from "./business-ui";
import { EnterpriseField, fieldErrors } from "./enterprise-fields";
import { ResourceSelect } from "./resource-select";
import { useTenant } from "./tenant-workspace";
import { productApi, type Product } from "@/lib/business-api";
import { operationsApi, type Supplier } from "@/lib/operations-api";
import { purchaseApi, type Purchase, type PurchaseLine, type PurchaseLineInput, type PurchasePayload } from "@/lib/purchase-api";

type Row = PurchaseLineInput & { key: string; selected: Pick<Product,"id"|"name"> | null };
function LineEditor({row,index,onChange,onRemove,canRemove}:{row:Row;index:number;onChange:(row:Row)=>void;onRemove:()=>void;canRemove:boolean}) {
  const tenant=useTenant();
  const products=useCallback((search:string,page:number)=>productApi.list(tenant.id,{search,page,is_active:true}),[tenant.id]);
  return <fieldset className="rounded-xl border border-slate-200 p-4 mt-5"><legend>Línea {index+1}</legend><ResourceSelect label={`Producto o servicio ${index+1}`} selected={row.selected} onSelect={selected=>onChange({...row,selected,product:selected?.id??""})} loader={products} describe={item=>item.name}/><div className="form-grid mt-4">
    <label className="field">Cantidad {index+1}<input className="input" type="number" required min="0.001" max="999999999.999" step="0.001" value={row.quantity} onChange={event=>onChange({...row,quantity:event.target.value})}/></label>
    <label className="field">Costo unitario {index+1}<input className="input" type="number" required min="0" max="9999999999.9999" step="0.0001" value={row.unit_cost} onChange={event=>onChange({...row,unit_cost:event.target.value})}/></label>
    <label className="field">Impuesto de línea {index+1} (%)<input className="input" type="number" required min="0" max="100" step="0.01" value={row.tax_rate} onChange={event=>onChange({...row,tax_rate:event.target.value})}/></label>
    <button className="button secondary" type="button" disabled={!canRemove} onClick={onRemove}>Quitar línea {index+1}</button></div></fieldset>;
}

export function PurchaseForm({order,lines,currency,onClose,onSaved}:{order?:Purchase;lines?:PurchaseLine[];currency:string;onClose:()=>void;onSaved:(order:Purchase)=>void}) {
  const tenant=useTenant();const [supplier,setSupplier]=useState<Pick<Supplier,"id"|"name">|null>(order?{id:order.supplier,name:order.supplier_name}:null);
  const [data,setData]=useState<Omit<PurchasePayload,"supplier"|"lines">>({currency:order?.currency??currency,reference:order?.reference??"",notes:order?.notes??"",expected_on:order?.expected_on??null});
  const [rows,setRows]=useState<Row[]>(()=>lines?.map(line=>({...line,key:line.id,selected:{id:line.product,name:line.product_name_snapshot}}))??[{key:crypto.randomUUID(),selected:null,product:"",quantity:"1.000",unit_cost:"",tax_rate:"0.00"}]);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [fields,setFields]=useState<Record<string,string>>({});
  const suppliers=useCallback((search:string,page:number)=>operationsApi.suppliers(tenant.id,{search,page,is_active:true}),[tenant.id]);
  async function save(event:FormEvent){event.preventDefault();if(!supplier)return;setBusy(true);setError("");setFields({});try{const result=await purchaseApi.save(tenant.id,{...data,supplier:supplier.id,lines:rows.map(({product,quantity,unit_cost,tax_rate})=>({product,quantity,unit_cost,tax_rate}))},order?.id);onSaved(result);}catch(error){setError(errorMessage(error));setFields(fieldErrors(error));}finally{setBusy(false);}}
  return <Modal title={order?"Editar borrador de compra":"Nuevo pedido de compra"} onClose={onClose} busy={busy}><form onSubmit={save}><p className="notice-info">Los costos se acuerdan por línea y moneda. Guardar o confirmar el pedido no genera stock, deuda ni pagos. El servidor calcula los importes con precisión decimal.</p>{error&&<Alert>{error}</Alert>}<ResourceSelect label="Proveedor del pedido" selected={supplier} onSelect={setSupplier} loader={suppliers} describe={item=>item.name}/><div className="form-grid mt-4">
    <EnterpriseField id="purchase-reference" label="Referencia del pedido" error={fields.reference}><input id="purchase-reference" className="input" maxLength={120} value={data.reference} onChange={event=>setData({...data,reference:event.target.value})}/></EnterpriseField>
    <EnterpriseField id="purchase-currency" label="Moneda del pedido" error={fields.currency}><input id="purchase-currency" className="input" required minLength={3} maxLength={3} value={data.currency} onChange={event=>setData({...data,currency:event.target.value.toUpperCase()})}/></EnterpriseField>
    <EnterpriseField id="purchase-expected" label="Recepción prevista (opcional)" error={fields.expected_on}><input id="purchase-expected" className="input" type="date" value={data.expected_on??""} onChange={event=>setData({...data,expected_on:event.target.value||null})}/></EnterpriseField>
    <EnterpriseField id="purchase-notes" label="Notas del pedido" error={fields.notes}><textarea id="purchase-notes" className="input" maxLength={2000} value={data.notes} onChange={event=>setData({...data,notes:event.target.value})}/></EnterpriseField></div>
    {rows.map((row,index)=><LineEditor key={row.key} row={row} index={index} canRemove={rows.length>1} onRemove={()=>setRows(rows.filter(item=>item.key!==row.key))} onChange={next=>setRows(rows.map(item=>item.key===row.key?next:item))}/>)}<button className="button secondary mt-4" type="button" disabled={rows.length>=100||busy} onClick={()=>setRows([...rows,{key:crypto.randomUUID(),selected:null,product:"",quantity:"1.000",unit_cost:"",tax_rate:"0.00"}])}>Agregar línea</button><footer className="form-footer"><button className="button secondary" type="button" disabled={busy} onClick={onClose}>Cancelar</button><button className="button" disabled={busy}>{busy?"Guardando…":"Guardar borrador de compra"}</button></footer></form></Modal>;
}
