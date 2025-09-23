# Plastic-Waste-Detection-YOLOv5
## Introduction
Welcome to the repository for the project "Plastic Waste Detection using YOLOv5s on Raspberry Pi 4B"! This project focuses on utilizing computer vision techniques to detect and classify plastic waste in real-time using the YOLOv5s object detection model, implemented on a Raspberry Pi 4B. The plastic waste detection classify the waste into PET, HDPE, PP and Non Recycleables.

## Project Higlights
- **YOLOv5s** : We employ the YOLOv5s (You Only Look Once version 5 small) object detection model as the core of our system. YOLOv5s offers a good balance between accuracy and speed, making it suitable for real-time applications on resource-constrained devices like the Raspberry Pi 4B.
You can find the documentation of YOLOv5 in here : https://github.com/ultralytics/yolov5.git 
- **Raspberry Pi 4B** : The Raspberry Pi 4B serves as the hardware platform for our project. Its compact size, low power consumption, and GPIO (General Purpose Input/Output) capabilities make it an ideal choice for edge computing and IoT applications.
- **Real-time Detection** :  Our implementation enables real-time detection and classification of plastic waste objects captured by the Webcam.

# Repository Structure
- Dataset Preparation
- Model Training
- Detection
 
# Dataset Preparation
The "Plastic Waste Detection using YOLOv5s on Raspberry Pi 4B" project utilizes a custom dataset consisting of 6000 images. These images were captured to encompass various types of plastic waste commonly found in the environment, including plastic bottles, plastic bags, plastic cups, cables, soap bottles, and styrofoam.
![Dataset-01](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/9a147cfc-ac14-4545-9663-c8ede095e4fa)

To train the YOLOv5s model effectively, the dataset was annotated using the Roboflow platform. Roboflow provides a user-friendly interface and annotation tools that facilitate the annotation process, saving time and effort.
![image](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/82bf27d2-4ea2-43ad-97a1-ed7003a5b5d8)


The annotations include bounding boxes that specify the location and size of each plastic waste object within the images. These annotations are crucial for training the model to accurately detect and classify plastic waste objects.


# Model Training
The "Plastic Waste Detection using YOLOv5s on Raspberry Pi 4B" model has been trained using the YOLOv5s architecture implemented with the PyTorch framework. The choice of YOLOv5s is based on a balance between model accuracy and size, making it suitable for deployment on resource-constrained devices like the Raspberry Pi.

## Dataset Proportion
The dataset used for training the model has been divided into three main subsets: training, validation, and testing. The proportions of these subsets are as follows:
- **Training:** 70% of the dataset is allocated for training the YOLOv5s model. This subset is used to teach the model to detect and classify plastic waste objects accurate
- **Validation:** 20% of the dataset is set aside for validation purposes. This subset helps evaluate the model's performance during the training process, allowing for fine-tuning and parameter optimization.
- **Testing:** The remaining 10% of the dataset is dedicated to testing the trained model's performance. This subset provides an independent evaluation of the model's ability to generalize to unseen plastic waste scenarios.

## Training Process
To train the "Plastic Waste Detection using YOLOv5s on Raspberry Pi 4B" model with the specified parameters, you can follow the steps outlined below:
1. **Load the necessary framework and libraries:**
```
!git clone https://github.com/ultralytics/yolov5  # clone repository from ultralytics
%cd yolov5

%pip install -qr requirements.txt # install dependencies
%pip install -q roboflow

import torch
import os
from IPython.display import Image, clear_output  # to display images

print(f"Setup complete. Using torch {torch.__version__} ({torch.cuda.get_device_properties(0).name if torch.cuda.is_available() else 'CPU'})")
```
2. **Assamble the dataset**
```
# set up environment
os.environ["DATASET_DIRECTORY"] = "/content/datasets"
```
```
from roboflow import Roboflow
rf = Roboflow(api_key="Your Roboflow API KEY")
project = rf.workspace("workspace").project("project name")
dataset = project.version(1).download("yolov5")
```

3. **Train the model**

The training process involves feeding the annotated dataset to the YOLOv5s model and optimizing its parameters to minimize the detection errors. This process iterates over multiple epochs, with each epoch representing a complete pass through the entire training dataset.

During training, the model learns to identify various plastic waste objects by adjusting its internal weights. The loss function used guides the model to minimize the discrepancies between the predicted bounding boxes and the ground truth annotations.
```
!python train.py --img 416 --batch 16 --epochs 200 --data {dataset.location}/data.yaml --weights y
[... omitted 256 of 512 lines ...]

RGB)
    	img = Image.fromarray(image)
    	img = img.resize((self.size, self.size), Image.BICUBIC)
    	img = F.to_tensor(img).unsqueeze(0)

    	# Perform inference
    	start = time.time()
    	with torch.no_grad():
        	img = img.to(self.device)
        	pred = self.model(img)[0]
    	end = time.time()
    	inference_time = end - start

    	# Process the outputs
    	pred = non_max_suppression(pred, self.confidence, self.threshold)[0]

    	# Prepare the results
    	predictions = []
    	if pred is not None and len(pred) > 0:
        	# Rescale bounding boxes to original image size
        	pred[:, :4] = scale_coords(img.shape[2:], pred[:, :4], image.shape).round()

        	# Iterate over detections and create prediction dictionary
        	for *box, conf, class_id in pred:
            	x1, y1, x2, y2 = box
            	box = [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
            	confidence = float(conf)
            	class_id = int(class_id)

            	prediction = {
                	'box': box,
                	'confidence': confidence,
                	'class_id': class_id
            	}
            	predictions.append(prediction)

    	return predictions, inference_time

def scale_coords(img_shape, coords, img0_shape):
	# Rescale coordinates to original image size
	gain = min(img_shape[0] / img0_shape[0], img_shape[1] / img0_shape[1])
	pad_x = (img_shape[1] - img0_shape[1] * gain) / 2
	pad_y = (img_shape[0] - img0_shape[0] * gain) / 2
	coords[:, [0, 2]] -= pad_x
	coords[:, [1, 3]] -= pad_y
	coords[:, :4] /= gain
	clip_coords(coords, img0_shape)
	return coords.round()

def clip_coords(coords, img_shape):
	# Clip bounding coordinates to image shape
	coords[:, 0].clamp_(0, img_shape[1])  # x1
	coords[:, 1].clamp_(0, img_shape[0])  # y1
	coords[:, 2].clamp_(0, img_shape[1])  # x2
	coords[:, 3].clamp_(0, img_shape[0])  # y2
	return coords
```
![Proto-01](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/a2922ff8-55fb-4201-af80-42c92b6861b6)
![Proto-04](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/5f080f62-a81b-4f0b-8d58-1c9ed4864a0a)



## The Result of Detection

After deploying YOLOv5 on Raspberry Pi 4 running Ubuntu, the model achieved impressive performance metrics with an average frame rate of 2 frames per second (2fps). The model also demonstrated high accuracy and precision in object detection tasks.

Performance Metrics:

- Accuracy: 97.2%
- Precision: 0.9995
- Recall: 0.9993
- F1 Score: 0.9994

![Precision](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/448654ea-7c99-45d4-b724-e01bd91511a9)
![Recall](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/3cddf19f-e86c-40c7-99e2-297de3c4c856)
![mAP_0 95](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/902c3208-8fb6-4c9a-bd1a-4a3bd0c7aac0)


In addition to the high accuracy and precision, the average computation time for processing each frame was measured to be 6.594 seconds. This computation time indicates the duration required for the model to analyze and detect objects within a single frame.

Please note that the actual computation time may vary depending on factors such as the complexity of the scene, the number of objects present, and the specific hardware configuration. It's recommended to optimize these parameters and consider the specific requirements of your application to achieve the best performance.

With these remarkable performance metrics and efficient computation time, YOLOv5 on Raspberry Pi 4 proves to be a powerful and reliable solution for real-time object detection tasks, enabling various applications in fields such as surveillance, robotics, and smart environments.

![mAP_0 95](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/b5d39a23-5505-40f0-9aca-fe5d10667c88)

![Precision](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/f185b869-cea2-4a6c-8d7d-28003fb8f742)
![Recall](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/6a1b116a-3647-46be-9a58-0948ad0d3693)
![F1_curve](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/b876f061-d364-433d-95e3-dc8330c2fb23)


![WhatsApp Image 2023-06-23 at 14 18 29](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/7d18e1e6-0fec-454d-a311-8b5ed0a2eb7b)
![WhatsApp Image 2023-06-23 at 14 18 20](https://github.com/has-bi/Plastic-Waste-Detection-YOLOv5s-Raspberry-Pi4/assets/117572919/ec82732f-19cf-48e6-a8ee-5ddb34876b38)


## Reference :
https://github.com/ultralytics/yolov5

https://github.com/weirros/yolov5_wi_pi4

https://jordan-johnston271.medium.com/tutorial-running-yolov5-machine-learning-detection-on-a-raspberry-pi-4-3938add0f719

https://pub.towardsai.net/yolov5-m-implementation-from-scratch-with-pytorch-c8f84a66c98b

https://github.com/the-raspberry-pi-guy/lcd
