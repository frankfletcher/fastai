# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/15_callback.hook.ipynb (unless otherwise specified).

__all__ = ['Hook', 'hook_output', 'Hooks', 'hook_outputs', 'dummy_eval', 'model_sizes', 'num_features_model',
           'has_params', 'HookCallback', 'total_params', 'layer_info', 'module_summary', 'ActivationStats']

# Cell
from ..basics import *

# Cell
@docs
class Hook():
    "Create a hook on `m` with `hook_func`."
    def __init__(self, m, hook_func, is_forward=True, detach=True, cpu=False, gather=False):
        store_attr('hook_func,detach,cpu,gather')
        f = m.register_forward_hook if is_forward else m.register_backward_hook
        self.hook = f(self.hook_fn)
        self.stored,self.removed = None,False

    def hook_fn(self, module, input, output):
        "Applies `hook_func` to `module`, `input`, `output`."
        if self.detach:
            input,output = to_detach(input, cpu=self.cpu, gather=self.gather),to_detach(output, cpu=self.cpu, gather=self.gather)
        self.stored = self.hook_func(module, input, output)

    def remove(self):
        "Remove the hook from the model."
        if not self.removed:
            self.hook.remove()
            self.removed=True

    def __enter__(self, *args): return self
    def __exit__(self, *args): self.remove()

    _docs = dict(__enter__="Register the hook",
                 __exit__="Remove the hook")

# Cell
def _hook_inner(m,i,o): return o if isinstance(o,Tensor) or is_listy(o) else list(o)

def hook_output(module, detach=True, cpu=False, grad=False):
    "Return a `Hook` that stores activations of `module` in `self.stored`"
    return Hook(module, _hook_inner, detach=detach, cpu=cpu, is_forward=not grad)

# Cell
@docs
class Hooks():
    "Create several hooks on the modules in `ms` with `hook_func`."
    def __init__(self, ms, hook_func, is_forward=True, detach=True, cpu=False):
        self.hooks = [Hook(m, hook_func, is_forward, detach, cpu) for m in ms]

    def __getitem__(self,i): return self.hooks[i]
    def __len__(self):       return len(self.hooks)
    def __iter__(self):      return iter(self.hooks)
    @property
    def stored(self):        return L(o.stored for o in self)

    def remove(self):
        "Remove the hooks from the model."
        for h in self.hooks: h.remove()

    def __enter__(self, *args): return self
    def __exit__ (self, *args): self.remove()

    _docs = dict(stored = "The states saved in each hook.",
                 __enter__="Register the hooks",
                 __exit__="Remove the hooks")

# Cell
def hook_outputs(modules, detach=True, cpu=False, grad=False):
    "Return `Hooks` that store activations of all `modules` in `self.stored`"
    return Hooks(modules, _hook_inner, detach=detach, cpu=cpu, is_forward=not grad)

# Cell
def dummy_eval(m, size=(64,64)):
    "Evaluate `m` on a dummy input of a certain `size`"
    ch_in = in_channels(m)
    x = one_param(m).new(1, ch_in, *size).requires_grad_(False).uniform_(-1.,1.)
    with torch.no_grad(): return m.eval()(x)

# Cell
def model_sizes(m, size=(64,64)):
    "Pass a dummy input through the model `m` to get the various sizes of activations."
    with hook_outputs(m) as hooks:
        _ = dummy_eval(m, size=size)
        return [o.stored.shape for o in hooks]

# Cell
def num_features_model(m):
    "Return the number of output features for `m`."
    sz,ch_in = 32,in_channels(m)
    while True:
        #Trying for a few sizes in case the model requires a big input size.
        try:
            return model_sizes(m, (sz,sz))[-1][1]
        except Exception as e:
            sz *= 2
            if sz > 2048: raise e

# Cell
def has_params(m):
    "Check if `m` has at least one parameter"
    return len(list(m.parameters())) > 0

# Cell
@funcs_kwargs
class HookCallback(Callback):
    "`Callback` that can be used to register hooks on `modules`"
    _methods = ["hook"]
    hook = noops
    def __init__(self, modules=None, every=None, remove_end=True, is_forward=True, detach=True, cpu=True, include_paramless=False , **kwargs):
        store_attr('modules,every,remove_end,is_forward,detach,cpu, include_paramless')
        assert not kwargs

    def before_fit(self):
        "Register the `Hooks` on `self.modules`."
        if self.modules is None: self.modules = [m for m in flatten_model(self.model) if self.include_paramless or has_params(m)]
        if self.every is None: self._register()

    def before_batch(self):
        if self.every is None: return
        if self.training and self.train_iter%self.every==0: self._register()

    def after_batch(self):
        if self.every is None: return
        if self.training and self.train_iter%self.every==0: self._remove()

    def after_fit(self):
        "Remove the `Hooks`."
        if self.remove_end: self._remove()

    def _register(self): self.hooks = Hooks(self.modules, self.hook, self.is_forward, self.detach, self.cpu)
    def _remove(self):
        if getattr(self, 'hooks', None): self.hooks.remove()

    def __del__(self): self._remove()

# Cell
def total_params(m):
    "Give the number of parameters of a module and if it's trainable or not"
    params = sum(p.numel() for p in m.parameters())
    trains = [p.requires_grad for p in m.parameters()]
    return params, trains[0] if trains else False

# Cell
def layer_info(learn, *xb):
    "Return layer infos of `model` on `xb` (only support batch first inputs)"
    def _track(m, i, o):
        params, trainable, shape = '', '', ''
        same = any((isinstance(x[0], torch.Tensor) and x[0].shape[1:] == x[1].shape for x in zip(i, o)))
        shape = apply(lambda x: x.shape, o)
        if hasattr(m, 'weight'): # non activation layer
            params, trainable = total_params(m)
        return (type(m).__name__, params, trainable, shape, same)

    with Hooks(flatten_model(learn.model), _track) as h:
        batch = apply(lambda o:o[:1], xb)
        train_only_cbs = [cb for cb in learn.cbs if hasattr(cb, '_only_train_loop')]
        with learn.removed_cbs(train_only_cbs), learn.no_logging(), learn as l:
            r = l.get_preds(dl=[batch], inner=True, reorder=False)
        return h.stored

# Cell
def _get_shapes(o, bs):
    inp = o[first(o)] if (isinstance(o, dict)) else o
    return ' x '.join([str(bs)] + [str(t) for t in inp[1:]])

def _print_shapes(o, bs):
    if isinstance(o, torch.Size): return _get_shapes(o, bs)
    elif isinstance(o, tuple): return _get_shapes(o[0], bs)
    else: return str([_print_shapes(x, bs) for x in o])

# Cell
def module_summary(learn, *xb):
    "Print a summary of `model` using `xb`"
    #Individual parameters wrapped in ParameterModule aren't called through the hooks in `layer_info`,
    #  thus are not counted inside the summary
    #TODO: find a way to have them counted in param number somehow
    infos = layer_info(learn, *xb)
    n,bs = 76,find_bs(xb)
    inp_sz = _print_shapes(apply(lambda x:x.shape, xb), bs)
    res = f"{type(learn.model).__name__} (Input shape: {inp_sz})\n"
    res += "=" * n + "\n"
    res += f"{'Layer (type)':<20} {'Output Shape':<20} {'Param #':<10} {'Trainable':<10}\n"
    res += "=" * n
    ps,trn_ps,j = 0,0,0
    infos = [o for o in infos if o is not None] #see comment in previous cell
    prev_sz = None
    for typ,np,trn,sz,chnged in infos:
        if sz is None: continue
        if j == 0:
            res += f'\n{"":<20} {_print_shapes(sz, bs)[:19]:<20}' # to avoid a double line at the top
        if not chnged and prev_sz != sz and j > 0: res += "\n" + "_" * n + "\n" + f'{"":<20} {_print_shapes(sz, bs)[:19]:<20}'
        j = 1
        res += f"\n{typ:<20} {'':<20} {np:<10} {str(trn):<10}"
        if np != '':
            ps += np
            if trn: trn_ps += np
        prev_sz = sz
    res += "\n" + "_" * n + "\n"
    res += f"\nTotal params: {ps:,}\n"
    res += f"Total trainable params: {trn_ps:,}\n"
    res += f"Total non-trainable params: {ps - trn_ps:,}\n\n"
    return PrettyString(res)

# Cell
@patch
def summary(self:Learner):
    "Print a summary of the model, optimizer and loss function."
    xb = self.dls.train.one_batch()[:getattr(self.dls.train, "n_inp", 1)]
    res = module_summary(self, *xb)
    res += f"Optimizer used: {self.opt_func}\nLoss function: {self.loss_func}\n\n"
    if self.opt is not None:
        res += "Model " + (
            "unfrozen\n\n"
            if self.opt.frozen_idx == 0
            else f"frozen up to parameter group #{self.opt.frozen_idx}\n\n"
        )

    res += "Callbacks:\n" + '\n'.join(f"  - {cb}" for cb in self.cbs.sorted('order'))
    return PrettyString(res)

# Cell
@delegates()
class ActivationStats(HookCallback):
    "Callback that record the mean and std of activations."
    order=-20
    def __init__(self, with_hist=False, **kwargs):
        super().__init__(**kwargs)
        self.with_hist = with_hist

    def before_fit(self):
        "Initialize stats."
        super().before_fit()
        self.stats = L()

    def hook(self, m, i, o):
        if isinstance(o, tuple): return self.hook_multi_ouput(o)
        o = o.float()
        res = {'mean': o.mean().item(), 'std': o.std().item(),
               'near_zero': (o<=0.05).long().sum().item()/o.numel()}
        if self.with_hist: res['hist'] = o.histc(40,0,10)
        return res

    def hook_multi_ouput(self,o_tuple):
        "For outputs of RNN which are [nested] tuples of tensors"
        return [
            self.hook(None, None, o)
            for o in self._flatten_tuple(o_tuple)
            if (isinstance(o, Tensor))
        ]

    def _flatten_tuple(self, o_tuple):
        "Recursively flatten a [nested] tuple"
        res = []
        for it in o_tuple:
            res += self._flatten_tuple(it) if isinstance(it, tuple) else [it]
        return tuple(res)

    def after_batch(self):
        "Take the stored results and puts it in `self.stats`"
        if self.training and (self.every is None or self.train_iter%self.every == 0):
            self.stats.append(self.hooks.stored)
        super().after_batch()

    def layer_stats(self, idx):
        lstats = self.stats.itemgot(idx)
        return L(lstats.itemgot(o) for o in ('mean','std','near_zero'))

    def hist(self, idx):
        res = self.stats.itemgot(idx).itemgot('hist')
        return torch.stack(tuple(res)).t().float().log1p()

    def color_dim(self, idx, figsize=(10,5), ax=None):
        "The 'colorful dimension' plot"
        res = self.hist(idx)
        if ax is None: ax = subplots(figsize=figsize)[1][0]
        ax.imshow(res, origin='lower')
        ax.axis('off')

    def plot_layer_stats(self, idx):
        _,axs = subplots(1, 3, figsize=(12,3))
        for o,ax,title in zip(self.layer_stats(idx),axs,('mean','std','% near zero')):
            ax.plot(o)
            ax.set_title(title)