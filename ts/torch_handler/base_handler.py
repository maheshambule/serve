"""
Base default handler to load torchscript or eager mode [state_dict] models
Also, provides handle method per torch serve custom model specification
"""
import abc
import logging
import os
import pathlib
import importlib.util
import torch
from torch.utils.cpp_extension import load
from ..utils.util import list_classes_from_module, load_label_mapping

logger = logging.getLogger(__name__)


class BaseHandler(abc.ABC):
    """
    Base default handler to load torchscript or eager mode [state_dict] models
    Also, provides handle method per torch serve custom model specification
    """
    def __init__(self):
        self.model = None
        self.mapping = None
        self.device = None
        self.initialized = False
        self.context = None
        self.manifest = None
        self.map_location = None
        self.torch_cpp_python_module = None
        self.torch_api_type = "python"

    def initialize(self, context):
        """First try to load torchscript else load eager mode state_dict based model"""

        properties = context.system_properties
        self.map_location = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.device = torch.device(self.map_location + ":" + str(properties.get("gpu_id"))
                                   if torch.cuda.is_available() else self.map_location)
        self.manifest = context.manifest

        model_dir = properties.get("model_dir")
        serialized_file = self.manifest['model']['serializedFile']
        model_pt_path = os.path.join(model_dir, serialized_file)

        if not os.path.isfile(model_pt_path):
            raise RuntimeError("Missing the model.pt file")

        # model def file
        model_file = self.manifest['model'].get('modelFile', '')
        self.torch_api_type = properties["torch_api_type"]

        if self.torch_api_type == 'python':
            if model_file:
                logger.debug('Loading eager model')
                self.model = self._load_pickled_model(model_dir, model_file, model_pt_path)
            else:
                logger.debug('Loading Torch Script model using Python API')
                self.model = self._load_torchscript_model(model_pt_path)

            self.model.to(self.device)
            self.model.eval()

        elif self.torch_api_type == 'cpp':
            if model_file:
                raise Exception("Eager models are not supported using CPP API")

            logger.info('Loading Torch Script model using CPP API')
            source_path = pathlib.Path(__file__).parent.absolute()
            cpp_source_path = os.path.join(source_path, "torch_cpp_python_bindings.cpp")
            self.torch_cpp_python_module = load(name="torch_cpp_python_bindings",
                                                sources=[cpp_source_path], verbose=True)
            self.model = self.torch_cpp_python_module.load_model(model_pt_path, self.map_location, str(self.device))
        else:
            raise Exception("Only Python and CPP APIs are supported.")

        logger.debug('Model file %s loaded successfully', model_pt_path)

        # Load class mapping for classifiers
        mapping_file_path = os.path.join(model_dir, "index_to_name.json")
        self.mapping = load_label_mapping(mapping_file_path)

        self.initialized = True

    def _load_torchscript_model(self, model_pt_path):
        return torch.jit.load(model_pt_path, map_location=self.map_location)

    def _load_pickled_model(self, model_dir, model_file, model_pt_path):
        model_def_path = os.path.join(model_dir, model_file)
        if not os.path.isfile(model_def_path):
            raise RuntimeError("Missing the model.py file")

        module = importlib.import_module(model_file.split(".")[0])
        model_class_definitions = list_classes_from_module(module)
        if len(model_class_definitions) != 1:
            raise ValueError("Expected only one class as model definition. {}".format(
                model_class_definitions))

        model_class = model_class_definitions[0]
        state_dict = torch.load(model_pt_path, map_location=self.map_location)
        model = model_class()
        model.load_state_dict(state_dict)
        return model

    def preprocess(self, data):
        """
        Override to customize the pre-processing
        :param data: Python list of data items
        :return: input tensor on a device
        """
        return torch.as_tensor(data, device=self.device)

    def inference(self, data, *args, **kwargs):
        """
        Override to customize the inference
        :param data: Torch tensor, matching the model input shape
        :return: Prediction output as Torch tensor
        """
        marshalled_data = data.to(self.device)
        with torch.no_grad():
            if self.torch_api_type == 'python':
                results = self.model(marshalled_data, *args, **kwargs)
            else:
                if len(kwargs):
                    raise Exception("Keyword arguments are not supported by CPP API. Use Python API instead.")
                params = [marshalled_data]
                params.extend(args)
                results = self.torch_cpp_python_module.run_model(self.model, params)
        return results

    def postprocess(self, data):
        """
        Override to customize the post-processing
        :param data: Torch tensor, containing prediction output from the model
        :return: Python list
        """

        return data.tolist()

    def handle(self, data, context):
        """
        Entry point for default handler
        """

        # It can be used for pre or post processing if needed as additional request
        # information is available in context
        self.context = context

        data = self.preprocess(data)
        data = self.inference(data)
        data = self.postprocess(data)
        return data
