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
\brief    Definition of interface IEnumerationT
\ingroup GenApi_PublicInterface
*/

#ifndef GENAPI_IENUMERATIONT_H
#define GENAPI_IENUMERATIONT_H

#include <GenApi/GenApiDll.h>
#include <GenApi/Types.h>
#include <GenApi/Pointer.h>
#include <GenApi/IEnumeration.h>
#include <GenApi/Compatibility.h>
#include <vector>

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // Enumeration template interface
    //*************************************************************

    /**
    \brief Interface for enumeration properties
    \ingroup GenApi_PublicInterface
    */
    template< typename EnumT >
    interface IEnumerationT  : public IEnumeration
    {
        //! Set node value
        /*!
        \param Value The value to set
        \param Verify Enables AccessMode and Range verification (default = true)
        */
        virtual void SetValue(EnumT Value, bool Verify = true) = 0;

        //! Set node value
        virtual IEnumeration& operator=(EnumT Value) = 0;

        //! Get node value
        /*!
        \param Verify Enables Range verification (default = false). The AccessMode is always checked
        \param IgnoreCache If true the value is read ignoring any caches (default = false)
        \return The value read
        */
        virtual EnumT GetValue(bool Verify = false, bool IgnoreCache = false) = 0;

        //! Get node value
        virtual EnumT operator()() = 0;

        //! Set node value
        /*! Note : the operator= is not inherited thus the operator= versions
        from IEnumeration must be implemented again */
        virtual IEnumeration& operator=(const GENICAM_NAMESPACE::gcstring& ValueStr) = 0;

        //! returns the EnumEntry object belonging to the Value
        virtual IEnumEntry *GetEntry(const EnumT Value) = 0;

        //! Get the current entry
        virtual IEnumEntry *GetCurrentEntry(bool Verify = false, bool IgnoreCache = false) = 0;

    };

    //*************************************************************
    // CEnumerationTRef class
    //*************************************************************

#ifndef DOXYGEN_IGNORE

    /**
    \internal
    \brief Reference to an IEnumerationT pointer
    \ingroup GenApi_PublicImpl
    */
    template< class EnumT >
    class CEnumerationTRef : public IEnumerationT< EnumT >, public IReference, public IEnumReference
    {
    public:
        // Constructor
        CEnumerationTRef() :
          m_Ptr(NULL)
          {}

          /*--------------------------------------------------------*/
          // IReference
          /*--------------------------------------------------------*/

          //! sets the implementation to the reference
          virtual void SetReference( IBase *ptr )
          {
              m_Ptr = dynamic_cast< IEnumeration *>( ptr );
          }

          /*--------------------------------------------------------*/
          // IEnumReference
          /*--------------------------------------------------------*/

          //! sets the number of enum values
          virtual void SetNumEnums( int NumEnums )
          {
              m_EnumExists.resize(NumEnums);
              m_EnumValues.resize(NumEnums);

              std::vector<bool>::iterator ptr;
              for(ptr = m_EnumExists.begin(); ptr != m_EnumExists.end(); ptr++)
                  *ptr = false;

          }

          //! sets the Enum value corresponding to a value
          virtual void SetEnumReference( int Index, GENICAM_NAMESPACE::gcstring Name)
          {
              if ( m_Ptr )
              {
                  CEnumEntryPtr ptrEnumEntry = GetEntryByName(Name);

                  if( ptrEnumEntry.IsValid() )
                  {
                      m_EnumExists[Index] = true;
                      m_EnumValues[Index] = ptrEnumEntry->GetValue();
                  }
              }
          }


          /*--------------------------------------------------------*/
          // IBase
          /*--------------------------------------------------------*/

          //! Get the access mode of the node
          virtual EAccessMode GetAccessMode() const
          {
              if(m_Ptr)
                  return m_Ptr->GetAccessMode();
              else
                  return NI;
          }

          /*--------------------------------------------------------*/
          // IValue
          /*--------------------------------------------------------*/

          //! Get the INode interface of the node
          virtual INode* GetNode()
          {
              if(m_Ptr)
                  return m_Ptr->GetNode();
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Get content of the node as string
          virtual GENICAM_NAMESPACE::gcstring ToString(bool Verify = false, bool IgnoreCache = false)
          {
              if(m_Ptr)
                  return m_Ptr->ToString(Verify, IgnoreCache);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Set content of the node as string
          virtual void FromString(const GENICAM_NAMESPACE::gcstring& ValueStr, bool Verify = true)
          {
              if(m_Ptr)
                  return m_Ptr->FromString(ValueStr, Verify);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Checks if the value comes from cache or is requested from another node
          bool IsValueCacheValid() const
          {
              if(m_Ptr)
                  return m_Ptr->IsValueCacheValid();
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          /*--------------------------------------------------------*/
          // IEnumeration
          /*--------------------------------------------------------*/

          //! Get list of symbolic Values
          virtual void GetSymbolics(StringList_t & Symbolics)
          {
              if(m_Ptr)
                  return m_Ptr->GetSymbolics(Symbolics);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Get list of entry nodes
          virtual void GetEntries(NodeList_t & Entries)
          {
              if(m_Ptr)
                  return m_Ptr->GetEntries(Entries);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Set node value
          virtual IEnumeration& operator=(const GENICAM_NAMESPACE::gcstring& ValueStr)
          {
              if(m_Ptr)
                  return m_Ptr->operator=(ValueStr);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Set node value
          virtual IEnumeration& operator=(const char *pValueStr)
          {
              if(m_Ptr)
                  return m_Ptr->operator=(pValueStr);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Set node value
          virtual void SetIntValue(int64_t Value, bool Verify = true)
          {
              if(m_Ptr)
                  m_Ptr->SetIntValue(Value, Verify);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Get node value
          virtual GENICAM_NAMESPACE::gcstring operator*()
          {
              if(m_Ptr)
                  return m_Ptr->operator*();
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Get node value
          virtual int64_t GetIntValue(bool Verify = false, bool IgnoreCache = false)
          {
              if(m_Ptr)
                  return m_Ptr->GetIntValue(Verify, IgnoreCache);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Get an entry node by name
          virtual IEnumEntry *GetEntryByName(const GENICAM_NAMESPACE::gcstring& Symbolic)
          {
              if(m_Ptr)
                  return m_Ptr->GetEntryByName(Symbolic);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }


          //! Get an entry node by its IntValue
          virtual IEnumEntry *GetEntry(const int64_t IntValue)
          {
              if(m_Ptr)
                  return m_Ptr->GetEntry(IntValue);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Get the current entry
          virtual IEnumEntry *GetCurrentEntry(bool Verify = false, bool IgnoreCache = false)
          {
              if(m_Ptr)
                  return m_Ptr->GetCurrentEntry(Verify, IgnoreCache);
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          /*--------------------------------------------------------*/
          // IEnumerationT
          /*--------------------------------------------------------*/

          //! Set node value
          virtual void SetValue(EnumT Value, bool Verify = true)
          {
              if(m_Ptr)
              {
                  if( m_EnumExists[Value] )
                  {
                      int64_t EnumValue = m_EnumValues[Value];
                      m_Ptr->SetIntValue(EnumValue, Verify);
                  }
                  else
                      throw ACCESS_EXCEPTION("EnumEntry %d not present", Value);
              }
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Set node value
          virtual IEnumeration& operator=(EnumT Value)
          {
              SetValue(Value);
              return *this;
          }

          //! Get node value
          virtual EnumT GetValue(bool Verify = false, bool IgnoreCache = false)
          {
              if(m_Ptr)
              {
                  int64_t IntValue = m_Ptr->GetIntValue(Verify, IgnoreCache);
                  std::vector<int64_t>::iterator ptr;
                  for ( unsigned int idx = 0; idx < m_EnumValues.size(); ++idx )
                  {
                      if( m_EnumExists[idx] &&  m_EnumValues[idx] == IntValue)
                          return (EnumT) idx;
                  }
                  throw ACCESS_EXCEPTION("Unknown IntValue %" FMT_I64 "d", IntValue);
              }
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

          //! Get node value
          virtual EnumT operator()()
          {
              return GetValue();
          }

          //! returns the EnumEntry object belonging to the Value
          virtual IEnumEntry *GetEntry(const EnumT Value)
          {
              if(m_Ptr)
              {
                  if( m_EnumExists[Value] )
                  {
                      int64_t EnumValue = m_EnumValues[Value];
                      return m_Ptr->GetEntry(EnumValue);
                  }
                  else
                      return NULL;
              }
              else
                  throw ACCESS_EXCEPTION("Feature not present (reference not valid)");
          }

    protected:
        //! Pointer to the implementation the reference references to
        IEnumeration *m_Ptr;

        //! The values for enums with a given index
        std::vector<int64_t > m_EnumValues;

        //! Indicates it an enum with a given index exists
        std::vector<bool > m_EnumExists;

    };

#endif

}

#endif // ifndef GENAPI_IENUMERATIONT_H
