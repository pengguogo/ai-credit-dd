import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = process.argv[2] || path.dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(await fs.readFile(path.join(root, 'workbook-data.json'), 'utf8'));
const wb = Workbook.create();
const status = {succeeded:'成功',needs_confirmation:'待确认',failed:'失败',runner_error:'执行异常'};
const cols = n => String.fromCharCode(64+n);
function sheet(name, title, headers, rows, widths, rowHeight=30) {
  const s = wb.worksheets.add(name);
  s.showGridLines = false;
  const last = cols(headers.length);
  s.getRange(`A1:${last}${rows.length+5}`).format.font = {name:'Arial',size:11,color:'#172033'};
  s.getRange('A2').values = [[title]];
  s.getRange('A2').format.font = {name:'Arial',size:16,bold:true,color:'#172033'};
  s.getRange(`A4:${last}4`).values = [headers];
  s.getRange(`A4:${last}4`).format = {fill:'#263B57',font:{name:'Arial',size:11,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',rowHeight:34,wrapText:true};
  if(rows.length) s.getRange(`A5:${last}${rows.length+4}`).values=rows;
  s.getRange(`A5:${last}${rows.length+4}`).format.rowHeight=rowHeight;
  s.getRange(`A5:${last}${rows.length+4}`).format.verticalAlignment='center';
  for(let i=0;i<widths.length;i++) s.getRange(`${cols(i+1)}1:${cols(i+1)}${rows.length+5}`).format.columnWidthPx=widths[i];
  s.freezePanes.freezeRows(4);
  s.freezePanes.freezeColumns(1);
  s.tables.add(`A4:${last}${rows.length+4}`,true,headers.length===10?'ApplicationTable':'QuestionTable');
  return s;
}

const summary = wb.worksheets.add('汇总与运行');
summary.showGridLines=false;
summary.getRange('A1:I34').format.font={name:'Arial',size:11,color:'#172033'};
summary.getRange('A2').values=[['赛题04公开集评测']];
summary.getRange('A2').format.font={name:'Arial',size:16,bold:true};
summary.getRange('A4:I4').values=[['类别','题数','成功','待确认','失败','平均秒','P95秒','Token','有证据题数']];
for(let n=0;n<2;n++) {
  const r=n+5, kind=n===0?'申请':'问询', m=data.metrics[n===0?'applications':'questions'];
  summary.getRange(`A${r}:I${r}`).values=[[kind,null,null,null,null,null,m.p95Seconds,null,null]];
  summary.getRange(`B${r}:F${r}`).formulas=[[
    `=COUNTIFS($A$13:$A$32,A${r})`,
    `=COUNTIFS($A$13:$A$32,A${r},$C$13:$C$32,"成功")`,
    `=COUNTIFS($A$13:$A$32,A${r},$C$13:$C$32,"待确认")`,
    `=COUNTIFS($A$13:$A$32,A${r},$C$13:$C$32,"失败")+COUNTIFS($A$13:$A$32,A${r},$C$13:$C$32,"执行异常")`,
    `=AVERAGEIFS($D$13:$D$32,$A$13:$A$32,A${r})`]];
  summary.getRange(`H${r}:I${r}`).formulas=[[
    `=SUMIFS($E$13:$E$32,$A$13:$A$32,A${r})`,
    `=COUNTIFS($A$13:$A$32,A${r},$F$13:$F$32,">0")`]];
}
summary.getRange('A8').values=[['运行成功不等于业务答对。两类并发执行，耗时含失败。P95采用nearest-rank。']];
summary.getRange('A9').values=[[data.fieldSummary]];
summary.getRange('A10').values=[['来源：同批results.jsonl与数据库证据；业务参考为主办方公开答案。完整回答见同目录CSV。']];
summary.getRange('A12:H12').values=[['类别','编号','终态','耗时秒','Token','证据数','错误码','runId']];
summary.getRange('A13:H32').values=data.runs.map(r=>[r.kind,r.id,status[r.status]||r.status,r.seconds,r.tokens,r.evidence,r.error,r.runId]);
for(const range of ['A4:I4','A12:H12']) summary.getRange(range).format={fill:'#263B57',font:{name:'Arial',size:11,color:'#FFFFFF',bold:true},horizontalAlignment:'center',rowHeight:30};
summary.getRange('A5:I6').format.rowHeight=30;
summary.getRange('A13:H32').format.rowHeight=27;
summary.getRange('D13:D32').setNumberFormat('0.00');
summary.getRange('F5:G6').setNumberFormat('0.00');
summary.getRange('E13:F32').setNumberFormat('#,##0');
summary.getRange('H5:H6').setNumberFormat('#,##0');
[110,95,110,110,120,110,170,240,130].forEach((w,i)=>summary.getRange(`${cols(i+1)}1:${cols(i+1)}34`).format.columnWidthPx=w);
summary.freezePanes.freezeRows(12);
summary.tables.add('A12:H32',true,'RunsTable');
summary.tabColor='#263B57';
const app=sheet('申请字段比对','10笔申请：评级与额度',
 ['申请','终态','系统评级','参考评级','评级严格一致','系统额度（万元）','参考额度（万元）','数值区间精确一致','包含于参考区间','复核说明'],
 data.applications.map(r=>[r.id,status[r.status]||r.status,r.risk,r.referenceRisk,r.riskExact?'一致':'不一致',r.amount??'未提取',r.referenceAmount,r.exact,r.within,r.note]),
 [95,100,105,110,130,145,150,145,130,350],65);
app.getRange('F5:G14').setNumberFormat('@');
app.getRange('J5:J14').format.wrapText=true;
const q=sheet('问询复核','10道问询：参考要点复核',
 ['编号','终态','问询','复核结论','差异与依据'],
 data.questions.map(r=>[r.id,status[r.status]||r.status,r.question,r.verdict,r.note]),
 [80,105,300,150,720],95);
q.getRange('C5:E14').format.wrapText=true;
for(const [s,range] of [[summary,'C13:C32'],[app,'B5:B14'],[q,'B5:B14']]) {
  s.getRange(range).conditionalFormats.add('containsText',{text:'失败',format:{fill:'#FCE5E5',font:{color:'#9C1B1B'}}});
  s.getRange(range).conditionalFormats.add('containsText',{text:'待确认',format:{fill:'#FFF1CD',font:{color:'#77570A'}}});
}
wb.recalculate();
console.log((await wb.inspect({kind:'region',sheetId:'汇总与运行',range:'A4:I6',maxChars:2200,tableMaxRows:3,tableMaxCols:9})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
for(const [name,range] of [['申请字段比对','A2:J14']]) {
 const blob=await wb.render({sheetName:name,range,scale:1,format:'png'});
 await fs.writeFile(path.join(root,`${name}-preview.png`),new Uint8Array(await blob.arrayBuffer()));
}
const outputDir=path.join(root,'outputs','dd04-public-latest');
await fs.mkdir(outputDir,{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(outputDir,'公开评测结果.xlsx'));
console.log('Excel已导出');
