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
\brief  Definition of interface INodeMapDyn
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_INODEMAPDYN_H
#define GENAPI_INODEMAPDYN_H

#include "Base/GCBase.h"
#include "INodeMap.h"

#ifdef _MSC_VER
#   pragma warning ( push )
#   pragma warning ( disable : 4251 ) // XXX needs to have dll-interface to be used by clients of class YYY
#endif

namespace GENAPI_NAMESPACE
{

    //*************************************************************
    // INodeMap interface
    //*************************************************************

    /**
    \brief Interface to access the node map
    \ingroup GenApi_PublicInterface
    */
    interface GENAPI_DECL_ABSTRACT INodeMapDyn : virtual public INodeMap
    {
        //! Deletes all Nodes from the map
        virtual void ClearAllNodes() = 0;

        //! Loads an XML from a file
        virtual void LoadXMLFromFile(const GENICAM_NAMESPACE::gcstring& FileName) = 0;

        //! Loads an XML from a file with injection
        virtual void LoadXMLFromFileInject(const GENICAM_NAMESPACE::gcstring& TargetFileName, const GENICAM_NAMESPACE::gcstring& InjectFileName) = 0;

        //! Loads an XML from a string
        virtual void LoadXMLFromString(const GENICAM_NAMESPACE::gcstring& XMLData) = 0;

        //! Loads an XML from a string with injection
        virtual void LoadXMLFromStringInject(const GENICAM_NAMESPACE::gcstring& TargetXMLData, const GENICAM_NAMESPACE::gcstring& InjectXMLData) = 0;

        //! Loads an XML, checks it for correctness, pre-processes it, caches it, and optionally applies a style sheet, and optionally writes it to a file
        virtual void PreprocessXMLFromFile(
            const GENICAM_NAMESPACE::gcstring& XMLFileName,          //!> The name of the XML file to process
            const GENICAM_NAMESPACE::gcstring& StyleSheetFileName,   //!> Optional name of a style sheet which is applied after the pre-processor (can be empty string)
                                                           //!> This has no effect if the OutputFileName is an empty string
            const GENICAM_NAMESPACE::gcstring& OutputFileName,       //!> Optional name of an output file into which the processed data is written (can be empty string)
            const uint32_t XMLValidation = xvDefault      //!> Optional bit mask formed from EXMLValidation enumeration indicating which tests should be performed on the XML file
            ) = 0;

        //! Injects an XML file into a target file
        virtual void MergeXMLFiles(
            const GENICAM_NAMESPACE::gcstring& TargetFileName,      //!> Name of the target XML file to process
            const GENICAM_NAMESPACE::gcstring& InjectedFileName,    //!> Name of the Injected XML file to process
            const GENICAM_NAMESPACE::gcstring& OutputFileName       //!> Name of the oputput file
            ) = 0;

        //! Extract independent subtree
        virtual void ExtractIndependentSubtree(
            const GENICAM_NAMESPACE::gcstring& XMLData,            //!> The XML data the subtree is extracted from.
            const GENICAM_NAMESPACE::gcstring& InjectXMLData,      //!> Optional XML data that is injected before extracting the subtree. No effect if an empty string is passed.
            const GENICAM_NAMESPACE::gcstring& SubTreeRootNodeName,//!> The name of the node that represents the root of the subtree that shall be extracted.
            GENICAM_NAMESPACE::gcstring& ExtractedSubtree          //!> The returned extracted subtree as string.
            ) = 0;

        //! Gets a list of supported schema versions
        /*! Each list entry is a string with the format "<Major>.<Minor>" were <Major> and <Minor> are integers
            Example: {"1.1", "1.2"} indicates that the schema v1.1 and v1.2 are supported.
            The SubMinor version number is not given since it is for fully compatible bug fixes only
        */
        virtual void GetSupportedSchemaVersions( GENICAM_NAMESPACE::gcstring_vector &SchemaVersions ) = 0;

        //! Loads an XML from a ZIP file
        virtual void LoadXMLFromZIPFile(const GENICAM_NAMESPACE::gcstring & ZipFileName) = 0;

        //! Loads an XML from a ZIP data buffer
        virtual void LoadXMLFromZIPData(const void* zipData, size_t zipSize) = 0;

        //! Loads a Zipped XML, checks it for correctness, pre-processes it, caches it, and optionally applies a style sheet, and optionally writes it to a file
        virtual void PreprocessXMLFromZIPFile(
            const GENICAM_NAMESPACE::gcstring& XMLFileName,          //!> The name of the XML file to process
            const GENICAM_NAMESPACE::gcstring& StyleSheetFileName,   //!> Optional name of a style sheet which is applied after the pre-processor (can be empty string)
                                                           //!> This has no effect if the OutputFileName is an empty string
            const GENICAM_NAMESPACE::gcstring& OutputFileName,       //!> Optional name of an output file into which the processed data is written (can be empty string)
            const uint32_t XMLValidation = xvDefault      //!> Optional bit mask formed from EXMLValidation enumeration indicating which tests should be performed on the XML file
            ) = 0;
    };

}

#ifdef _MSC_VER
#   pragma warning ( pop )
#endif

#endif // ifndef GENAPI_INODEMAPDYN_H
