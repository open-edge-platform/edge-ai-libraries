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
\brief    Definition of CNodeMapRef
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_NODEMAPREF_H
#define GENAPI_NODEMAPREF_H

#include <GenICamVersion.h>
#include <Base/GCString.h>
#include <Base/GCException.h>

#include <GenApi/Pointer.h>
#include <GenApi/INodeMap.h>
#include <GenApi/IDestroy.h>
#include <GenApi/NodeMapFactory.h>

#include <cstdlib>

namespace GENAPI_NAMESPACE
{

#   ifdef _WIN32

    // see below in the Linux branch
    inline IDestroy *CastToIDestroy(INodeMap *pNodeMap)
    {
        return dynamic_cast<IDestroy *>(pNodeMap);
    }

#   else
    //! makes sure the dynamic_cast operator is implemented in the DLL (due to a Linux bug)
    GENAPI_DECL IDestroy *CastToIDestroy(INodeMap *pNodeMap);
#   endif

    /**
    \brief Smartpointer template for NodeMaps with create function
    \ingroup GenApi_PublicInterface
    \tparam TCameraParams  The camera specific parameter class (auto generated from camera xml file)
    */
    template<class TCameraParams>
    class CNodeMapRefT : public TCameraParams
    {
    public:
        //! Constructor
        CNodeMapRefT(const GENICAM_NAMESPACE::gcstring &DeviceName = "Device");

        //! Constructor
        CNodeMapRefT(INodeMap* pNodeMap, const GENICAM_NAMESPACE::gcstring &DeviceName = "Device");

        //! Copy constructor
        CNodeMapRefT(const CNodeMapRefT& Them);

        //! Assignment
        CNodeMapRefT& operator=(const CNodeMapRefT& Them);

        //! Assignment of an INodeMap*
        CNodeMapRefT& operator=(INodeMap* pNodeMap);

        //! Destructor
        virtual ~CNodeMapRefT();

        //! Destroys the node map
        void _Destroy();

        //! Creates the object from a XML file with given file name
        void _LoadXMLFromFile(const GENICAM_NAMESPACE::gcstring &FileName);

        //! Creates the object from a ZIP'd XML file with given file name
        void _LoadXMLFromZIPFile(const GENICAM_NAMESPACE::gcstring &ZipFileName);

        //! Creates the object from a ZIP'd XML file given in a string
        void _LoadXMLFromZIPData(const void* zipData, size_t zipSize);

        //! Creates the object from a XML target and an inject file with given file name
        void _LoadXMLFromFileInject(const GENICAM_NAMESPACE::gcstring &TargetFileName, const GENICAM_NAMESPACE::gcstring &InjectFileName);

        //! Creates the object from XML data given in a string
        void _LoadXMLFromString(const GENICAM_NAMESPACE::gcstring& XMLData);

        //! Creates the object from XML data given in a string with injection
        void _LoadXMLFromStringInject(const GENICAM_NAMESPACE::gcstring& TargetXMLDataconst, const GENICAM_NAMESPACE::gcstring& InjectXMLData);

        //! Gets a list of supported schema versions
        /*! Each list entry is a string with the format "{Major}.{Minor}" were {Major} and {Minor} are integers
        Example: {"1.1", "1.2"} indicates that the schema v1.1 and v1.2 are supported.
        The SubMinor version number is not given since it is for fully compatible bug fixes only
        */
        virtual void _GetSupportedSchemaVersions(GENICAM_NAMESPACE::gcstring_vector &SchemaVersions) const;

        //! Get device name
        virtual GENICAM_NAMESPACE::gcstring _GetDeviceName() const;

        //! Fires nodes which have a polling time
        virtual void _Poll(int64_t ElapsedTime);

        //! Clears the cache of the camera description files
        static bool _ClearXMLCache();

        //----------------------------------------------------------------
        // INodeMap
        //----------------------------------------------------------------

        //! Retrieves all nodes in the node map
        virtual void _GetNodes(NodeList_t &Nodes) const;

        //! Retrieves the node from the central map by name
        virtual INode* _GetNode(const GENICAM_NAMESPACE::gcstring& key) const;

        //! Invalidates all nodes
        virtual void _InvalidateNodes() const;

        //! Connects a port to a port node with given name
        virtual bool _Connect(IPort* pPort, const GENICAM_NAMESPACE::gcstring& PortName) const;

        //! Connects a port to the standard port "Device"
        virtual bool _Connect(IPort* pPort) const;

        //! Parse all Swissknife equations
        virtual bool _ParseSwissKnifes( GENICAM_NAMESPACE::gcstring_vector *pErrorList = NULL ) const;
        //! Pointer to the NodeMap
        INodeMap *_Ptr;

    private:
        //! The name of this device
        GENICAM_NAMESPACE::gcstring _DeviceName;
        
        //ATTENTION: not thread safe
        int* _pRefCount;
        void Release();
        void Attach(INodeMap *pNodeMap, const GENICAM_NAMESPACE::gcstring &DeviceName, int* pRefCount);
    };



    template<class TCameraParams>
    inline CNodeMapRefT<TCameraParams>::CNodeMapRefT(const GENICAM_NAMESPACE::gcstring &DeviceName)
        : _Ptr(NULL)
        , _DeviceName(DeviceName)
        , _pRefCount(NULL)
    {
    }
    
    template<class TCameraParams>
    inline CNodeMapRefT<TCameraParams>::CNodeMapRefT(INodeMap *pNodeMap, const GENICAM_NAMESPACE::gcstring &DeviceName)
        : _Ptr(NULL)
        , _DeviceName(DeviceName)
        , _pRefCount(NULL)
    {
        assert(pNodeMap);
        Attach(pNodeMap, DeviceName, pNodeMap ? new int(0) : NULL);
    }
    
    template<class TCameraParams>
    GENAPI_NAMESPACE::CNodeMapRefT<TCameraParams>::CNodeMapRefT(const CNodeMapRefT& Them)
        : TCameraParams()
        , _Ptr(NULL)
        , _DeviceName()
        , _pRefCount(NULL)
    {
        Attach(Them._Ptr, Them._DeviceName, Them._pRefCount);
    }

    //ATTENTION: not thread safe
    template<class TCameraParams>
    void GENAPI_NAMESPACE::CNodeMapRefT<TCameraParams>::Attach(INodeMap *pNodeMap, const GENICAM_NAMESPACE::gcstring &DeviceName, int* pRefCount)
    {
        // Must be empty
        assert(_Ptr == NULL);
        assert(_pRefCount == NULL);

        //always copy device name
        if (&_DeviceName != &DeviceName) //if not assigning member itself
        {
            _DeviceName = DeviceName;
        }

        // Attach
        if (pNodeMap)
        {
            assert(pRefCount);
            if (pRefCount)
            {
                ++*pRefCount;

                //assign new node map data
                _Ptr = pNodeMap;
                _pRefCount = pRefCount;

                // Initialize the references
                TCameraParams::_Initialize(_Ptr);
            }
        }
    }
    
    //ATTENTION: not thread safe
    template<class TCameraParams>
    void GENAPI_NAMESPACE::CNodeMapRefT<TCameraParams>::Release()
    {
        if (_Ptr)
        {
            // Copy node map data for eventual later destruction
            INodeMap* pToDel = _Ptr;
            int* pRefCount = _pRefCount;

            // Clear
            _pRefCount = NULL;
            _Ptr = NULL;
            _DeviceName = "Device";

            assert(pRefCount);
            // Check if destruction is required
            if (pRefCount)
            {
                assert(*pRefCount > 0);
                --*pRefCount;
                if (*pRefCount == 0)
                {
                    // We do not need this anymore, all references are gone
                    delete pRefCount;
                    pRefCount = NULL;

                    // Destroy the node map finally
                    GENAPI_NAMESPACE::IDestroy *pDestroy = CastToIDestroy(pToDel);
                    assert(pDestroy);
                    pDestroy->Destroy(); //must not throw
                }
            }
        }
        else
        {
            // Must not have a refcount when no node map is there.
            assert(_pRefCount == NULL);
        }
    }

    template<class TCameraParams>
    CNodeMapRefT<TCameraParams>& GENAPI_NAMESPACE::CNodeMapRefT<TCameraParams>::operator=(INodeMap* pNodeMap)
    {
        Release();
        assert(pNodeMap);
        if (pNodeMap)
        {
            Attach(pNodeMap, pNodeMap->GetDeviceName(), new int(0));
        }

        return *this;
    }

    template<class TCameraParams>
    CNodeMapRefT<TCameraParams>& GENAPI_NAMESPACE::CNodeMapRefT<TCameraParams>::operator=(const CNodeMapRefT& Them)
    {
        Release();
        Attach(Them._Ptr, Them._DeviceName, Them._pRefCount);
        return *this;
    }

    template<class TCameraParams>
    inline CNodeMapRefT<TCameraParams>::~CNodeMapRefT()
    {
        Release();
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_Destroy()
    {
        Release();
    }


    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_LoadXMLFromFile(const GENICAM_NAMESPACE::gcstring &FileName)
    {
        // FileName environment is replaced in CNodeMapFactory ctor

        // Load the DLL
        if(_Ptr)
            throw RUNTIME_EXCEPTION("Node map already created");

        // Load the XML file
        CNodeMapFactory nodeMapData(ContentType_Xml, FileName);
        Attach(nodeMapData.CreateNodeMap(_DeviceName), _DeviceName, new int(0));
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_LoadXMLFromZIPFile(const GENICAM_NAMESPACE::gcstring &ZipFileName)
    {
        // FileName environment is replaced in CNodeMapFactory ctor

        // Load the DLL
        if(_Ptr)
            throw RUNTIME_EXCEPTION("Node map already created");

        // Load the XML file
        CNodeMapFactory nodeMapData(ContentType_ZippedXml, ZipFileName);
        Attach(nodeMapData.CreateNodeMap(), _DeviceName, new int(0));
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_LoadXMLFromFileInject(const GENICAM_NAMESPACE::gcstring &TargetFileName, const GENICAM_NAMESPACE::gcstring &InjectFileName)
    {
        // xxxFileName environment is replaced in CNodeMapFactory ctor

        // Load the DLL
        if(_Ptr)
            throw RUNTIME_EXCEPTION("Node map already created");

        // Load the XML file
        CNodeMapFactory nodeMapData(ContentType_Xml, TargetFileName);
        CNodeMapFactory injectNodeMapData(ContentType_Xml, InjectFileName);
        nodeMapData.AddInjectionData(injectNodeMapData);
        Attach(nodeMapData.CreateNodeMap(), _DeviceName, new int(0));
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_LoadXMLFromString(const GENICAM_NAMESPACE::gcstring& XMLData)
    {
        // Load the DLL
        if(_Ptr)
            throw RUNTIME_EXCEPTION("Node map already created");

        // Load the XML file
        CNodeMapFactory nodeMapData(ContentType_Xml, XMLData.c_str(), XMLData.size()); //avoid string copy
        Attach(nodeMapData.CreateNodeMap(_DeviceName), _DeviceName, new int(0));
    }


    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_LoadXMLFromZIPData(const void* zipData, size_t zipSize)
    {
        // Load the DLL
        if(_Ptr)
            throw RUNTIME_EXCEPTION("Node map already created");

        // Load the XML file
        CNodeMapFactory nodeMapData(ContentType_ZippedXml, zipData, zipSize);
        Attach(nodeMapData.CreateNodeMap(), _DeviceName, new int(0));
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_LoadXMLFromStringInject(const GENICAM_NAMESPACE::gcstring& TargetXMLData, const GENICAM_NAMESPACE::gcstring& InjectXMLData)
    {
        // Load the DLL
        if(_Ptr)
            throw RUNTIME_EXCEPTION("Node map already created");

        // Load the XML file
        CNodeMapFactory nodeMapData(ContentType_Xml, TargetXMLData.c_str(), TargetXMLData.size()); //avoid string copy
        CNodeMapFactory injectNodeMapData(ContentType_Xml, InjectXMLData.c_str(), InjectXMLData.size()); //avoid string copy
        nodeMapData.AddInjectionData(injectNodeMapData);
        Attach(nodeMapData.CreateNodeMap(), _DeviceName, new int(0));
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_GetSupportedSchemaVersions(GENICAM_NAMESPACE::gcstring_vector &SchemaVersions) const
    {
        CNodeMapFactory().GetSupportedSchemaVersions(SchemaVersions);
    }

    template<class TCameraParams>
    inline GENICAM_NAMESPACE::gcstring CNodeMapRefT<TCameraParams>::_GetDeviceName() const
    {
        if(_Ptr)
            return _Ptr->GetDeviceName();
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_Poll(int64_t ElapsedTime)
    {
        if(_Ptr)
            return _Ptr->Poll(ElapsedTime);
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_GetNodes(NodeList_t &Nodes) const
    {
        if(_Ptr)
            return _Ptr->GetNodes(Nodes);
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
    }

    template<class TCameraParams>
    inline INode* CNodeMapRefT<TCameraParams>::_GetNode(const GENICAM_NAMESPACE::gcstring& key) const
    {
        if(_Ptr)
            return _Ptr->GetNode(key);
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
    }

    template<class TCameraParams>
    inline void CNodeMapRefT<TCameraParams>::_InvalidateNodes() const
    {
        if(_Ptr)
            return _Ptr->InvalidateNodes();
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
    }

    template<class TCameraParams>
    inline bool CNodeMapRefT<TCameraParams>::_ParseSwissKnifes( GENICAM_NAMESPACE::gcstring_vector *pErrorList ) const
    {
        bool ret = false;
        if (_Ptr)
            ret = _Ptr->ParseSwissKnifes(pErrorList);
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
        return ret;
    }

    template<class TCameraParams>
    inline bool CNodeMapRefT<TCameraParams>::_Connect(IPort* pPort, const GENICAM_NAMESPACE::gcstring& PortName) const
    {
        if(_Ptr)
            return _Ptr->Connect(pPort, PortName);
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
    }

    template<class TCameraParams>
    inline bool CNodeMapRefT<TCameraParams>::_Connect(IPort* pPort) const
    {
        if(_Ptr)
            return _Ptr->Connect(pPort);
        else
            throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
    }


    template<class TCameraParams>
    inline bool CNodeMapRefT<TCameraParams>::_ClearXMLCache()
    {
        return CNodeMapFactory::ClearCache();
    }

    /**
    \brief Empty base class used by class CNodeMapRef as generic template argument
    \ingroup GenApi_PublicInterface
    */
    class CGeneric_XMLLoaderParams
    {
    protected:
        virtual void _Initialize(GENAPI_NAMESPACE::INodeMap*) {}
    };


    /**
    \brief Smartpointer for NodeMaps with create function
    \ingroup GenApi_PublicInterface
    \note This class is a simple typedef definition. The class syntax is only used,
    because Doxygen has to generate a useful documentation.
    */
    class CNodeMapRef : public CNodeMapRefT<GENAPI_NAMESPACE::CGeneric_XMLLoaderParams>
    {
    public:
        //! Constructor
        CNodeMapRef(const GENICAM_NAMESPACE::gcstring &DeviceName = "Device")
            : CNodeMapRefT<GENAPI_NAMESPACE::CGeneric_XMLLoaderParams>(DeviceName)
        {
        }

        //! Constructor
        CNodeMapRef(INodeMap* pNodeMap, const GENICAM_NAMESPACE::gcstring &DeviceName = "Device")
            : CNodeMapRefT<GENAPI_NAMESPACE::CGeneric_XMLLoaderParams>(pNodeMap, DeviceName)
        {
        }

        //! Copy constructor
        CNodeMapRef(const CNodeMapRef& Them)
            : CNodeMapRefT<GENAPI_NAMESPACE::CGeneric_XMLLoaderParams>(Them)
        {
        }

        //! Assignment
        CNodeMapRef& operator=(const CNodeMapRef& Them)
        {
            CNodeMapRefT<GENAPI_NAMESPACE::CGeneric_XMLLoaderParams>::operator=(Them);
            return *this;
        }

        //! Assignment of an INodeMap*
        CNodeMapRef& operator=(INodeMap* pNodeMap)
        {
            CNodeMapRefT<GENAPI_NAMESPACE::CGeneric_XMLLoaderParams>::operator=(pNodeMap);
            return *this;
        }
    };

}

#endif // ifndef GENAPI_NODEMAPPTR_H
