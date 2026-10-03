"""Tk desktop UI; all conversion work stays off the UI thread."""
from dataclasses import asdict
from pathlib import Path
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .engine import ConversionEngine,normalize_extension
from .model import Settings,Cancelled
from .tools import capabilities,capability_groups
from .interpretations import MODES,choices,effective
from .batch import BatchConverter


def scrollable(parent):
    canvas=tk.Canvas(parent,highlightthickness=0,bg='#f1f5f9')
    scrollbar=ttk.Scrollbar(parent,orient='vertical',command=canvas.yview)
    scrollbar.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    inner=ttk.Frame(canvas,padding=12); window=canvas.create_window((0,0),window=inner,anchor='nw')
    inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
    def wheel(event):
        if str(event.widget).startswith(str(parent)):
            canvas.yview_scroll(-int(event.delta/120),'units')
    parent.bind_all('<MouseWheel>',wheel,add='+')
    return inner


class App:
    def __init__(self,root):
        self.root=root; self.engine=ConversionEngine(); self.events=queue.Queue(); self.cancel=threading.Event()
        self.busy=False; self.preview_id=0; self.settings_vars={}; self.last_path=None
        self.input_paths=[]; self.preserve_names=tk.BooleanVar(value=True)
        self.suggested_source=''; self.suggested_extension=''
        self.interpretation=tk.StringVar(value=MODES['auto'][0])
        self.source=tk.StringVar(); self.extension=tk.StringVar(value='png'); self.output=tk.StringVar()
        self.detected=tk.StringVar(value='Choose a file to detect its contents')
        self.strategy=tk.StringVar(value='Preview a route before converting')
        self.status=tk.StringVar(value='Ready · files stay on your computer')
        root.title('Any2Any · Universal File Converter'); root.geometry('1080x850'); root.minsize(850,680)
        style=ttk.Style(root); style.theme_use('clam')
        style.configure('TFrame',background='#f1f5f9'); style.configure('TLabel',background='#f1f5f9',foreground='#0f172a',font=('Segoe UI',10))
        style.configure('Title.TLabel',font=('Segoe UI',25,'bold')); style.configure('Sub.TLabel',foreground='#475569')
        style.configure('Accent.TButton',font=('Segoe UI',11,'bold'),padding=10)
        outer=ttk.Frame(root,padding=22); outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Any2Any',style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer,text='Any file. Any extension. An honest explanation of what happens.',style='Sub.TLabel').pack(anchor='w',pady=(2,15))
        inputs=ttk.LabelFrame(outer,text=' 1 · Choose source and destination ',padding=12); inputs.pack(fill='x')
        inputs.columnconfigure(1,weight=1)
        ttk.Label(inputs,text='Input file').grid(row=0,column=0,sticky='w',padx=(0,12))
        self.source_entry=ttk.Entry(inputs,textvariable=self.source); self.source_entry.grid(row=0,column=1,sticky='ew',pady=5)
        ttk.Button(inputs,text='Browse…',command=self.browse).grid(row=0,column=2,padx=(8,0))
        ttk.Label(inputs,textvariable=self.detected,style='Sub.TLabel',wraplength=850).grid(row=1,column=0,columnspan=3,sticky='w',pady=4)
        ttk.Label(inputs,text='Output extension').grid(row=2,column=0,sticky='w')
        combo=ttk.Combobox(inputs,textvariable=self.extension,values='png jpg webp gif tiff pdf mp4 mov mkv avi webm wav mp3 flac ogg csv xlsx docx pptx txt json xml zip tar gz xyz'.split())
        combo.grid(row=2,column=1,sticky='ew',pady=5)
        combo.bind('<<ComboboxSelected>>',lambda e:self.suggest_output())
        combo.bind('<FocusOut>',lambda e:self.suggest_output())
        ttk.Label(inputs,text='Type any extension, including an unknown one.',style='Sub.TLabel').grid(row=3,column=1,sticky='w')
        ttk.Label(inputs,text='Save as').grid(row=4,column=0,sticky='w')
        ttk.Entry(inputs,textvariable=self.output).grid(row=4,column=1,sticky='ew',pady=5)
        ttk.Button(inputs,text='Location…',command=self.location).grid(row=4,column=2,padx=(8,0))
        self.drop_note=ttk.Label(inputs,text='Drop one or multiple files into the input field',style='Sub.TLabel'); self.drop_note.grid(row=5,column=1,sticky='w')
        try:
            from tkinterdnd2 import DND_FILES
            self.source_entry.drop_target_register(DND_FILES)
            self.source_entry.dnd_bind('<<Drop>>',self.drop)
        except (ImportError,AttributeError,tk.TclError): self.drop_note.configure(text='Drag-and-drop unavailable; use Browse (install tkinterdnd2 to enable it).')
        tabs=ttk.Notebook(outer); tabs.pack(fill='both',expand=True,pady=12)
        route=ttk.Frame(tabs,padding=12); tabs.add(route,text='Strategy & preview')
        ttk.Label(route,textvariable=self.strategy,font=('Segoe UI',12,'bold'),wraplength=940).pack(anchor='w')
        selector=ttk.Frame(route); selector.pack(fill='x',pady=(8,0))
        ttk.Label(selector,text='Interpretation').pack(side='left',padx=(0,10))
        self.interpretation_combo=ttk.Combobox(selector,textvariable=self.interpretation,state='readonly',width=48,
                                              values=[label for label,_ in MODES.values()])
        self.interpretation_combo.pack(side='left',fill='x',expand=True)
        self.interpretation_combo.bind('<<ComboboxSelected>>',lambda e:self.preview())
        self.route=tk.Text(route,height=5,wrap='word',font=('Segoe UI',10),bg='#ffffff',fg='#0f172a',relief='flat',padx=10,pady=10)
        self.route.pack(fill='x',pady=10); self.route.configure(state='disabled')
        ttk.Button(route,text='Preview selected route',command=self.preview).pack(anchor='w')
        self.thumb=ttk.Label(route,text='Route preview shows how the file will be interpreted.'); self.thumb.pack(anchor='w',pady=10)
        settings_tab=ttk.Frame(tabs); tabs.add(settings_tab,text='Conversion settings'); settings=scrollable(settings_tab)
        # Compact two-column settings grid fits a normal desktop window.
        specs=[('frame_mode','Video sampling','seconds',('seconds','frames','every','even','scene')),
               ('frame_interval','Sampling interval',5.0,None),('max_pages','Maximum pages / frames',50,None),
               ('seconds_per_page','Seconds per slide',2.0,None),('fps','Video FPS',24,None),
               ('width','Render width',1280,None),('height','Render height',720,None),
               ('transition','Slide transition','cut',('cut','fade')),('audio_seconds','Audio duration / preview seconds',8.0,None),
               ('sample_rate','Audio sample rate',22050,None),('audio_view','Audio visualization','waveform',('waveform','spectrogram','spectrum','stereo')),
               ('table_audio','Table sonification','pitch',('pitch','amplitude')),('max_read_bytes','Read / embedded bytes limit',16*1024*1024,None),
               ('max_cells','Spreadsheet cell limit',20000,None),('max_archive_bytes','Archive expanded byte limit',32*1024*1024,None),
               ('max_archive_entries','Archive entry limit',10000,None),('tool_timeout','External tool timeout (seconds)',600,None),
               ('font_size','Text font size',20,None),('background','Background color','#fafafa',None),
               ('video_view','Video frame view','sampling',('sampling','first','middle','last','contact','animated')),
               ('image_audio','Image audio mode','brightness',('brightness','rgb','scanline')),
               ('text_video','Text video mode','slides',('slides','scroll')),('table_video','Table video mode','sheets',('sheets','rows')),
               ('scene_threshold','Scene detection threshold',.3,None),('scroll_speed','Scroll pixels per second',40,None)]
        for index,(key,label,default,values) in enumerate(specs):
            col=(index%2)*2; row=index//2
            ttk.Label(settings,text=label).grid(row=row,column=col,sticky='w',padx=(0,10),pady=4)
            var=tk.StringVar(value=str(default)); self.settings_vars[key]=var
            widget=ttk.Combobox(settings,textvariable=var,values=values,state='readonly',width=17) if values else ttk.Entry(settings,textvariable=var,width=19)
            widget.grid(row=row,column=col+1,sticky='ew',padx=(0,18),pady=4)
        for index,(key,label,default) in enumerate([('timestamps','Video timestamps',True),('subtitles','Embed PDF text subtitles',False),
                    ('rgb_audio','Sonify RGB separately',False),('archive_text','Include safe readable archive members',False),('prefer_tts','Prefer local text-to-speech',True),
                    ('transcribe','Use offline speech recognition',False),('ocr','Use local OCR when available',True),
                    ('auto_height','Automatic text image height',True),('multi_image','Save separate images for all pages',True)]):
            var=tk.BooleanVar(value=default); self.settings_vars[key]=var
            ttk.Checkbutton(settings,text=label,variable=var).grid(row=14+index//2,column=(index%2)*2,columnspan=2,sticky='w',pady=3)
        ttk.Label(settings,text='Speech recognition uses existing local weights only. Multi-image outputs use .page-NNN filenames. Limits apply to interpretations; native media conversion streams the source.',style='Sub.TLabel',wraplength=900).grid(row=20,column=0,columnspan=4,sticky='w',pady=10)
        logs=ttk.Frame(tabs,padding=8); tabs.add(logs,text='Log & result')
        self.log_text=tk.Text(logs,wrap='word',font=('Consolas',10),bg='#101827',fg='#dbeafe',state='disabled')
        self.log_text.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(logs,command=self.log_text.yview); scrollbar.pack(side='right',fill='y'); self.log_text.configure(yscrollcommand=scrollbar.set)
        batch_tab=ttk.Frame(tabs,padding=10); tabs.add(batch_tab,text='Batch queue')
        ttk.Checkbutton(batch_tab,text='Preserve each input filename (collisions get unique names)',variable=self.preserve_names).pack(anchor='w',pady=(0,6))
        self.batch_tree=ttk.Treeview(batch_tab,columns=('source','destination','status','progress'),show='headings')
        for key,label,width in [('source','Input',230),('destination','Output',260),('status','Status',170),('progress','Progress',80)]:
            self.batch_tree.heading(key,text=label); self.batch_tree.column(key,width=width)
        self.batch_tree.pack(side='left',fill='both',expand=True)
        batch_scroll=ttk.Scrollbar(batch_tab,command=self.batch_tree.yview); batch_scroll.pack(side='right',fill='y')
        self.batch_tree.configure(yscrollcommand=batch_scroll.set)
        debug_tab=ttk.Frame(tabs,padding=10); tabs.add(debug_tab,text='Route diagnostics')
        self.diagnostics=tk.Text(debug_tab,wrap='word',font=('Consolas',10),state='disabled')
        self.diagnostics.pack(fill='both',expand=True)
        deps_tab=ttk.Frame(tabs); tabs.add(deps_tab,text='Capabilities'); deps=scrollable(deps_tab)
        ttk.Label(deps,text='Missing optional backends unlock extra features; they do not prevent other useful interpretations.',wraplength=920).pack(anchor='w',pady=8)
        for group in capability_groups():
            ttk.Label(deps,text=group['group'],font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(12,4))
            for item in group['items']:
                ttk.Label(deps,text=f'{item["name"]}: {item["status"]}',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=2)
                ttk.Label(deps,text=('Unlocks: ' if item['status']=='Missing' else 'Provides: ')+item['functionality'],wraplength=900).pack(anchor='w',pady=(0,3))
        footer=ttk.Frame(outer); footer.pack(fill='x')
        self.convert_button=ttk.Button(footer,text='Convert',style='Accent.TButton',command=self.convert); self.convert_button.pack(side='left')
        self.cancel_button=ttk.Button(footer,text='Cancel',command=lambda:self.cancel.set(),state='disabled'); self.cancel_button.pack(side='left',padx=8)
        ttk.Button(footer,text='Open output folder',command=self.open_folder).pack(side='right')
        self.progress=ttk.Progressbar(outer,maximum=100); self.progress.pack(fill='x',pady=(10,5))
        self.overall_progress=ttk.Progressbar(outer,maximum=100); self.overall_progress.pack(fill='x',pady=(0,5))
        ttk.Label(outer,textvariable=self.status,style='Sub.TLabel',wraplength=960).pack(anchor='w')
        root.protocol('WM_DELETE_WINDOW',self.close); root.after(80,self.poll)

    def get_settings(self):
        defaults=asdict(Settings()); values={}
        for key,var in self.settings_vars.items():
            value=var.get(); kind=type(defaults[key])
            values[key]=kind(value)
        values['mode']=next((key for key,(label,_) in MODES.items() if label==self.interpretation.get()),'auto')
        settings=Settings(**values); settings.validate(); return settings

    def browse(self):
        paths=filedialog.askopenfilenames(title='Choose one or multiple input files')
        if paths: self.set_inputs(paths)

    def drop(self,event):
        paths=self.root.tk.splitlist(event.data)
        if paths: self.set_inputs(paths)

    def set_inputs(self,paths):
        if self.busy: return
        self.input_paths=list(paths); self.source.set(paths[0]); self.interpretation.set(MODES['auto'][0])
        self.batch_tree.delete(*self.batch_tree.get_children())
        for index,path in enumerate(paths): self.batch_tree.insert('','end',iid=str(index),values=(Path(path).name,'Pending','Pending','0%'))
        self.suggest_output(force=True); self.preview()

    def suggest_output(self,force=False):
        try:
            source=Path(self.source.get()); ext=normalize_extension(self.extension.get())
            if not force and str(source)==self.suggested_source and ext==self.suggested_extension: return
            self.output.set(str(source.parent if len(self.input_paths)>1 else source.with_name(source.stem+'.converted.'+ext)))
            self.interpretation.set(MODES['auto'][0])
            self.suggested_source=str(source); self.suggested_extension=ext
        except Exception: pass

    def location(self):
        path=filedialog.askdirectory(title='Batch output folder') if len(self.input_paths)>1 else filedialog.asksaveasfilename(initialfile=Path(self.output.get()).name or 'converted.'+self.extension.get(),defaultextension='.'+self.extension.get().lstrip('.'))
        if path: self.output.set(path)

    def preview(self):
        if self.busy: return
        try: settings=self.get_settings(); extension=normalize_extension(self.extension.get())
        except Exception as error: messagebox.showerror('Invalid settings',str(error)); return
        self.preview_id+=1; request=self.preview_id; source=self.source.get()
        self.status.set('Detecting file and planning route…')
        def worker():
            try:
                info,plan=self.engine.preview(source,extension,settings)
                diagnostics=self.engine.planner.diagnostics(info,extension,effective(settings))
                self.events.put(('preview',(request,info,plan,diagnostics,extension)))
            except Exception as error: self.events.put(('preview_error',(request,str(error))))
        threading.Thread(target=worker,daemon=True).start()

    def convert(self):
        if self.busy: return
        try:
            settings=self.get_settings(); extension=normalize_extension(self.extension.get())
            if len(self.input_paths)>1 and self.source.get()==self.input_paths[0]:
                self.convert_batch(settings,extension); return
            destination=Path(self.output.get())
            if destination.suffix.lower()!='.'+extension:
                destination=destination.with_suffix('.'+extension); self.output.set(str(destination))
            if not self.source.get() or not self.output.get(): raise ValueError('Select input and output paths.')
        except Exception as error: messagebox.showerror('Invalid settings',str(error)); return
        overwrite=False
        existing=[path for path in [destination,*destination.parent.glob(destination.stem+'.page-*'+destination.suffix)] if path.exists()]
        if existing:
            overwrite=messagebox.askyesno('Overwrite outputs?',f'Replace these outputs only after validation succeeds?\n'+ '\n'.join(str(path) for path in existing[:20]))
            if not overwrite: return
        self.busy=True; self.cancel=threading.Event(); self.preview_id+=1
        self.convert_button.configure(state='disabled'); self.cancel_button.configure(state='normal'); self.progress['value']=0
        self.overall_progress['value']=0
        self.status.set('Converting…'); source=self.source.get()
        def worker():
            try:
                result=self.engine.convert(source,destination,settings,self.cancel,
                    log=lambda message:self.events.put(('log',message)),progress=lambda amount:self.events.put(('progress',amount)),overwrite=overwrite)
                self.events.put(('result',result))
            except Exception as error: self.events.put(('error',str(error)))
        threading.Thread(target=worker,daemon=True).start()

    def convert_batch(self,settings,extension):
        batch=BatchConverter(self.engine)
        items=batch.plan(self.input_paths,self.output.get(),extension,self.preserve_names.get())
        existing=[Path(item.destination) for item in items if Path(item.destination).exists()]
        for item in items:
            path=Path(item.destination); existing.extend(path.parent.glob(path.stem+'.page-*'+path.suffix))
        overwrite=False
        if existing:
            overwrite=messagebox.askyesno('Overwrite batch outputs?',f'Replace {len(existing)} existing outputs after each file validates?\n'+'\n'.join(str(path) for path in existing[:20]))
            if not overwrite: return
        self.busy=True; self.cancel=threading.Event(); self.preview_id+=1
        self.convert_button.configure(state='disabled'); self.cancel_button.configure(state='normal')
        self.progress['value']=0; self.overall_progress['value']=0
        def event(index,item,overall):
            self.events.put(('batch_progress',(index,item.source,item.destination,item.status,item.progress,item.error,overall)))
        def worker():
            result=batch.convert(items,settings,self.cancel,log=lambda message:self.events.put(('log',message)),event=event,overwrite=overwrite)
            self.events.put(('batch_result',result))
        threading.Thread(target=worker,daemon=True).start()

    def append_log(self,text):
        self.log_text.configure(state='normal'); self.log_text.insert('end',text+'\n'); self.log_text.see('end'); self.log_text.configure(state='disabled')

    def poll(self):
        for _ in range(100):
            try: kind,value=self.events.get_nowait()
            except queue.Empty: break
            if kind=='log':
                self.append_log(value)
                if value.startswith(('Native conversion:','Semantic conversion:','Binary interpretation:')):
                    self.strategy.set(value.split(':',1)[0])
                    self.route.configure(state='normal'); self.route.delete('1.0','end'); self.route.insert('end',value); self.route.configure(state='disabled')
            elif kind=='progress':
                self.progress['value']=max(float(self.progress['value']),value*100)
                self.overall_progress['value']=max(float(self.overall_progress['value']),value*100)
            elif kind=='preview':
                request,info,plan,diagnostics,extension=value
                if request!=self.preview_id: continue
                self.detected.set(f'{info.description} · {info.mime} · detected by {info.evidence}')
                self.strategy.set(plan.label+': '+plan.steps[-1].target.replace('output:','').upper())
                self.route.configure(state='normal'); self.route.delete('1.0','end'); self.route.insert('end',plan.route)
                if plan.priority>=2: self.route.insert('end','\n\nNo standard conversion is selected. This route interprets the contents for the destination medium.')
                if 'envelope' in plan.steps[-1].name: self.route.insert('end','\n\nOutput will contain a data envelope, not a codec for this extension.')
                self.route.configure(state='disabled'); self.status.set('Route ready. Settings can change the interpretation; choose binary to override.')
                self.show_thumbnail(info)
                keys=choices(info,extension)
                self.interpretation_combo.configure(values=[MODES[key][0] for key in keys])
                if self.interpretation.get() not in [MODES[key][0] for key in keys]: self.interpretation.set(MODES['auto'][0])
                self.diagnostics.configure(state='normal'); self.diagnostics.delete('1.0','end')
                for index,candidate in enumerate(diagnostics):
                    self.diagnostics.insert('end',f'Candidate {index+1}'+(' · SELECTED' if candidate['selected'] else '')+'\n'+candidate['route']+
                        f'\nScore: {candidate["score"]} · {candidate["classification"]} · '+('Available' if candidate['available'] else 'Missing: '+', '.join(candidate['blocked_by']))+'\n\n')
                self.diagnostics.configure(state='disabled')
                if len(self.input_paths)>1: self.status.set(f'{len(self.input_paths)} files queued. Preview shows the first input; each file plans its own route.')
            elif kind=='preview_error':
                request,message=value
                if request==self.preview_id: self.status.set(message); self.append_log(message)
            elif kind=='batch_progress':
                index,source,destination,status,progress,error,overall=value
                if self.batch_tree.exists(str(index)):
                    self.batch_tree.item(str(index),values=(Path(source).name,Path(destination).name,status+(': '+error[:80] if error else ''),f'{progress*100:.0f}%'))
                self.progress['value']=progress*100; self.overall_progress['value']=max(float(self.overall_progress['value']),overall*100)
                self.status.set(f'File {index+1}/{len(self.input_paths)} · {status} · {Path(source).name}')
            elif kind=='batch_result':
                self.busy=False; self.convert_button.configure(state='normal'); self.cancel_button.configure(state='disabled')
                completed=[item for item in value if item.status=='complete']; failed=[item for item in value if item.status=='failed']
                self.status.set(f'Batch finished · {len(completed)} complete · {len(failed)} failed · {sum(item.status=="cancelled" for item in value)} cancelled')
                if completed: self.last_path=completed[-1].destination
                self.append_log(json.dumps([asdict(item) for item in value],indent=2,ensure_ascii=False))
            elif kind in {'result','error'}:
                self.busy=False; self.convert_button.configure(state='normal'); self.cancel_button.configure(state='disabled')
                if kind=='error': self.status.set(value); self.append_log(value)
                else:
                    self.last_path=value.destination; self.strategy.set(value.classification)
                    self.append_log(json.dumps(asdict(value),indent=2,ensure_ascii=False))
                    self.status.set(f'Complete · {value.output_size:,} bytes · {value.duration:.2f}s · {value.destination}')
        self.root.after(80,self.poll)

    def show_thumbnail(self,info):
        if info.category!='image': self.thumb.configure(image='',text='Preview shows the planned interpretation. Full results appear after conversion.'); return
        try:
            from PIL import Image,ImageTk
            with Image.open(self.source.get()) as image:
                if image.width*image.height>40_000_000: return
                image.thumbnail((420,150)); self.thumbnail=ImageTk.PhotoImage(image.copy())
            self.thumb.configure(image=self.thumbnail,text='')
        except Exception: self.thumb.configure(image='',text='Input thumbnail unavailable; damaged inputs can still use binary interpretation.')

    def open_folder(self):
        path=Path(self.last_path or self.output.get()).absolute().parent
        if not path.is_dir(): return
        if os.name=='nt': os.startfile(path)
        else:
            import subprocess,sys
            subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path)])

    def close(self):
        if self.busy:
            self.cancel.set(); self.status.set('Cancelling and cleaning temporary files…')
            self.root.after(150,self.close_when_idle)
        else: self.root.destroy()

    def close_when_idle(self):
        if self.busy: self.root.after(150,self.close_when_idle)
        else: self.root.destroy()


def main():
    try:
        from tkinterdnd2 import TkinterDnD
        root=TkinterDnD.Tk()
    except (ImportError,RuntimeError,tk.TclError): root=tk.Tk()
    App(root); root.mainloop()
