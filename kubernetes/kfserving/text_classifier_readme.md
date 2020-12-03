# Serve a Text Classification Model in KFServing for Inference:

In this document, the .mar file creation, request & response on the KFServing side and the KFServing changes to the handler files for Text Classification model using Torchserve's default text handler.

## .mar file creation

The .mar file creation command is as below:

```bash
torch-model-archiver --model-name my_text_classifier --version 1.0 --model-file serve/examples/text_classification/model.py --serialized-file serve/examples/text_classification/model.pt --handler text_classifier --extra-files "serve/examples/text_classification/index_to_name.json,serve/examples/text_classification/source_vocab.pt"
```
## Request and Response

The curl request is as below:

```bash
 curl -H "Content-Type: application/json" --data @kubernetes/kfserving/kf_request_json/text_classifier.json http://127.0.0.1:8085/v1/models/my_tc:predict
```


The Prediction response is as below :

```bash
{
	"predictions" : [
	   {
		"World" : 0.0036
		"Sports" : 0.0065
		"Business" :0.9160
		"Sci/Tec" :0.079
	   }
	]
}
```



## KFServing changes to the handler files

* 1)  When you write a handler, always expect a plain Python list containing data ready to go into `preprocess`.

        The text classifier request difference between the regular torchserve and kfserving is as below

    ### Regular torchserve request:
	```
	[
		{
			"data" : "The recent climate change across world is impacting negatively"
		}     
	]
	```

	###	KFServing Request:
	```
	{

		"instances":[
						{
							"data" : "The recent climate change across world is impacting negatively"
						}
					]
	}
	```

    The KFServing request is unwrapped by the kfserving envelope in torchserve  and sent like a torchserve request. So effectively the values of  `instances`  key is sent to the handlers.

        

* 2)  The Request data for kfserving  is a batches of dicts as opposed to batches of bytes array(text file) in 		  the regular torchserve.

	  So  in the preprocess method of [text_classifier.py](https://github.com/pytorch/serve/blob/master/ts/torch_handler/text_classifier.py) KFServing doesn't require the data to be utf-8 decoded for text inputs, hence the code was modified to ensure that Torchserve Input Requests which are sent as text file are only utf-8 decoded and not for the KFServing Input Requests.