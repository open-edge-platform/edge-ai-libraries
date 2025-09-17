# setup.py
from setuptools import setup, find_packages

setup(
    name='video_chunking',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'typing',
        'ruptures',
        'opencv-python',
        'numpy',
        'scikit-image',
        'decord'
    ],
    author='LinJiaojiao',
    author_email='jiaojiao.lin@intel.com',
    description='A Python module for video chunking',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    # url='https://github.com/.../video_chunking',
    # classifiers=[
    #     'Programming Language :: Python :: 3',
    #     'License :: OSI Approved :: Apache Software License',
    #     'Operating System :: OS Independent',
    # ],
    python_requires='>=3.6',
)
