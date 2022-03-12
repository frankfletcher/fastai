# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/74_callback.azureml.ipynb (unless otherwise specified).

__all__ = ['AzureMLCallback']

# Cell
from ..basics import *
from ..learner import Callback

# Cell
from azureml.core.run import Run
from azureml.exceptions import RunEnvironmentException
import warnings

# Cell
class AzureMLCallback(Callback):
    """
    Log losses, metrics, model architecture summary to AzureML.

    If `log_offline` is False, will only log if actually running on AzureML.
    A custom AzureML `Run` class can be passed as `azurerun`.
    If `log_to_parent` is True, will also log to the parent run, if exists (e.g. in AzureML pipelines).
    """
    order = Recorder.order+1

    def __init__(self, azurerun=None, log_to_parent=True):
        if azurerun:
            self.azurerun = azurerun
        else:
            try:
                self.azurerun = Run.get_context(allow_offline=False)
            except RunEnvironmentException:
                # running locally
                self.azurerun = None
                warnings.warn("Not running on AzureML and no azurerun passed, AzureMLCallback will be disabled.")
        self.log_to_parent = log_to_parent

    def before_fit(self):
        self._log("n_epoch", self.learn.n_epoch)
        self._log("model_class", str(type(self.learn.model)))

        try:
            summary_file = Path("outputs") / 'model_summary.txt'
            with summary_file.open("w") as f:
                f.write(repr(self.learn.model))
        except:
            print('Did not log model summary. Check if your model is PyTorch model.')

    def after_batch(self):
        # log loss and opt.hypers
        if self.learn.training:
            self._log('batch__loss', self.learn.loss.item())
            self._log('batch__train_iter', self.learn.train_iter)
            for h in self.learn.opt.hypers:
                for k, v in h.items():
                    self._log(f'batch__opt.hypers.{k}', v)

    def after_epoch(self):
        # log metrics
        for n, v in zip(self.learn.recorder.metric_names, self.learn.recorder.log):
            if n not in ['epoch', 'time']:
                self._log(f'epoch__{n}', v)
            if n == 'time':
                # split elapsed time string, then convert into 'seconds' to log
                m, s = str(v).split(':')
                elapsed = int(m)*60 + int(s)
                self._log(f'epoch__{n}', elapsed)

    def _log(self, metric, value):
        if self.azurerun is not None:
            self.azurerun.log(metric, value)
            if self.log_to_parent and self.azurerun.parent is not None:
                self.azurerun.parent.log(metric, value)