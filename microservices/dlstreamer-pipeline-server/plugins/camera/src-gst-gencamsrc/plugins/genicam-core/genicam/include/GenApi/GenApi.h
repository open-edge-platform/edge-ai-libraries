//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Fritz Dierks
//  $Header$
//
//  License: This file is published under the license of the EMVA GenICam  Standard Group.
//  A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
//  If for some reason you are missing  this file please contact the EMVA or visit the website
//  (http://www.genicam.org) for a full copy.
//
//  THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
//  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
//  OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
//  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
//  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
//  ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
//  POSSIBILITY OF SUCH DAMAGE.
//-----------------------------------------------------------------------------
/*!
\file
\brief    Main include file for using GenApi with smart pointers
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_GENAPI_H
#define GENAPI_GENAPI_H

#include <Base/GCBase.h>
#include <Base/GCUtilities.h>
#include <GenApi/GenApiDll.h>
//#include <GenApi/impl/Log.h>
#include <GenApi/Pointer.h>
#include <GenApi/IBase.h>
#include <GenApi/INode.h>
#include <GenApi/IValue.h>
#include <GenApi/ICategory.h>
#include <GenApi/IInteger.h>
#include <GenApi/IFloat.h>
#include <GenApi/IRegister.h>
#include <GenApi/IEnumeration.h>
#include <GenApi/IEnumEntry.h>
#include <GenApi/IBoolean.h>
#include <GenApi/IPort.h>
#include <GenApi/IPortRecorder.h>
#include <GenApi/IPortConstruct.h>
#include <GenApi/IChunkPort.h>
#include <GenApi/IString.h>
#include <GenApi/INodeMap.h>
#include <GenApi/IDestroy.h>
#include <GenApi/IDeviceInfo.h>
#include <GenApi/ISelector.h>
#include <GenApi/ICommand.h>
#include <GenApi/IUserData.h>
#include <GenApi/NodeMapRef.h>
#include <GenApi/NodeCallback.h>
#include <GenApi/Persistence.h>
#include <GenApi/StructPort.h>
#include <GenApi/SelectorSet.h>

#if defined (_MSC_VER)
#   include <GenApi/GenApiLinkage.h>
#endif

#endif
