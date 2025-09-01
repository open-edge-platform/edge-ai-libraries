// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include <iostream>
#include <gflags/gflags.h>
#include <string>

using namespace std;

#define DATAPATH string("/opt/intel/orb_lze/samples/")

// @brief message for help argument
static const char help_message[] = "./feature_extract --images=<> --image_path=<> --threads=<>";

// @brief message for input number of images
static const char num_of_images_message[] = "Number of images or number of cameras. Default value: 1";

// @brief message for input image path
static const char image_path_message[] = "Path to input image files. Default value: image.jpg";

// @brief message for number of threads setting
static const char num_of_threads_message[] = "Number of threads to run. Default value: 1";

// @brief message for number of iterations setting
static const char num_of_iterations_message[] = "Number of iterations to run. Default value: 10";

// @brief Define flag for showing help message
DEFINE_bool(h, false, help_message);

// @brief Define num of input images or num of cameras.
DEFINE_int32(images, 1, num_of_images_message);

// @brief Define the image path.
DEFINE_string(image_path, DATAPATH+"market.jpg", image_path_message);

// @brief Define the number of thread.
DEFINE_int32(threads, 1, num_of_threads_message);

// @brief Define the number of iterations.
DEFINE_int32(iterations, 10, num_of_iterations_message);

static void showUsage()
{
   std::cout << std::endl;
   std::cout << "Following are the command line arguments:" << std::endl;
   std::cout << std::endl;
   std::cout << " Usage: " << help_message << std::endl;
   std::cout << std::endl;
   std::cout << "   --images <integer>     :  " << num_of_images_message << std::endl;
   std::cout << "   --image_path <string>  :  " << image_path_message << std::endl;
   std::cout << "   --threads <integer>    :  " << num_of_threads_message << std::endl;
   std::cout << "   --iterations <integer> :  " << num_of_iterations_message << std::endl;
   std::cout << std::endl;
   std::cout << std::endl;
}


bool ParseCommandLine(int argc, char *argv[])
{
   if( argc == 1)
   {
       showUsage();
       return false;
   }

   gflags::ParseCommandLineNonHelpFlags(&argc, &argv, true);
   if (FLAGS_h) {
      showUsage();
      return false;
   }
   if((FLAGS_images <= 0) || (FLAGS_images > 16)) {

       std::cerr << "Error:Number of images must be greater than 0 and not greater than 16" << std::endl;
       return false;
   }

   if( FLAGS_image_path.empty()) {
       std::cerr << "Error:Image path must not be empty" << std::endl;
       return false;
   }
   if((FLAGS_threads <= 0) || (FLAGS_threads > 16)) {
       std::cerr << "Error:Number of threads must be greater than 0 and not greater than 16" << std::endl;
       return false;
   }
   if((FLAGS_images * FLAGS_threads) > 64)
   {
       std::cerr << "Error:Maximum number of images and threads exceeded" << std::endl;
       std::cerr << "Total Count of images in all threads should not be more than 64" << std::endl;
       return false;
   }

   return true;
}
