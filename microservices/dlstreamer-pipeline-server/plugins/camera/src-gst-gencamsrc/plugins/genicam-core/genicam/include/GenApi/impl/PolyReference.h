//-----------------------------------------------------------------------------
//  (c) 2008 by Basler Vision Technologies
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
\brief    Definition of polymorphical smart pointer
\ingroup GenApi_Implementation
*/

#ifndef GENAPI_POLYREFERENCE_H
#define GENAPI_POLYREFERENCE_H

#include "Base/GCBase.h"
#include "GenApi/IBase.h"
#include "GenApi/IValue.h"
#include "GenApi/IFloat.h"
#include "GenApi/IInteger.h"
#include "GenApi/IEnumeration.h"
#include "GenApi/IBoolean.h"
#include "GenApi/IString.h"
#include "GenApi/impl/INodePrivate.h"
#include "GenApi/Pointer.h"
#include <limits>

#undef min
#undef max

namespace GENAPI_NAMESPACE
{
    inline int64_t round(double x)
    {
        return (int64_t)(x > 0.0 ? x + 0.5 : x - 0.5);
    }

    //inline int64_t abs(int64_t x)
    //{
    //    return (x >= 0 ? x : -x);
    //}

    inline double abs(double  x)
    {
        return (x >= 0.0 ? x : -x);
    }

    //! A reference to an int64 which can bei either an int64 variable,
    //! or a pointer to an IInteger, an IEnumeration, an IBoolean, or a IFloat
    class CIntegerPolyRef
    {
    public:
        //! Constructor
        CIntegerPolyRef() :
          m_Type(typeUninitialized)
          {
              m_Value.Value = 0;
          }

          //! set integer value
          void operator=(int64_t Value)
          {
              m_Type = typeValue;
              m_Value.Value = Value;
          }

		  //! set pointer
		  void operator=(INode *pValue)
		  {
			  operator=( dynamic_cast<IBase*>(pValue) );
		  }

          //! set pointer
          void operator=(IBase *pValue)
          {
              m_Value.pInteger = dynamic_cast<IInteger*>(pValue);
              if( m_Value.pInteger )
                  m_Type = typeIInteger;
              else
              {
                  m_Value.pEnumeration = dynamic_cast<IEnumeration*>(pValue);
                  if( m_Value.pEnumeration )
                      m_Type = typeIEnumeration;
                  else
                  {
                      m_Value.pBoolean = dynamic_cast<IBoolean*>(pValue);
                      if( m_Value.pBoolean )
                          m_Type = typeIBoolean;
                      else
                      {
                          m_Value.pFloat = dynamic_cast<IFloat*>(pValue);
                          if( m_Value.pFloat )
                              m_Type = typeIFloat;
                          else
                              throw RUNTIME_EXCEPTION("CIntegerPolyRef::operator(IBase*) : pointer is neither IInteger*, nor IEnumeration*, nor IBoolean*, nor IFloat*");
                      }
                  }
              }
          }

          //! True if the object references a pointer
          inline bool IsPointer() const
          {
              return (m_Type != typeValue) && (m_Type != typeUninitialized);
          }

		  //! True if the object references a pointer
		  inline bool IsValue() const
		  {
			  return (m_Type == typeValue) && (m_Type != typeUninitialized);
		  }

		  //! True if the object is initialized
          inline bool IsInitialized() const
          {
              return (m_Type != typeUninitialized);
          }

          //! returns the pointer referenced
          inline INodePrivate *GetPointer() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return dynamic_cast<INodePrivate*>(m_Value.pInteger);
              case typeIEnumeration:
                  return dynamic_cast<INodePrivate*>(m_Value.pEnumeration);
              case typeIBoolean:
                  return dynamic_cast<INodePrivate*>(m_Value.pBoolean);
              case typeIFloat:
                  return dynamic_cast<INodePrivate*>(m_Value.pFloat);
              case typeValue:
                  return NULL;
#           pragma BullseyeCoverage off
              case typeUninitialized:
              default:
                  return NULL;
#           pragma BullseyeCoverage on
              }
          }

          //! cast to INode (may be zero)
          inline operator INode*(void) const
          {
              return GetPointer();
          }

          //! see IInteger interface
          inline int64_t GetValue( bool Verify = false, bool IgnoreCache = false) const
          {
              switch(m_Type)
              {
              case typeValue:
                  return m_Value.Value;
              case typeIInteger:
                  return m_Value.pInteger->GetValue(Verify, IgnoreCache);
              case typeIEnumeration:
                  {
                      CEnumEntryPtr ptrEnumEntry = m_Value.pEnumeration->GetCurrentEntry(Verify, IgnoreCache);
                      return round(ptrEnumEntry->GetNumericValue());
                  }
              case typeIBoolean:
                  return m_Value.pBoolean->GetValue(Verify, IgnoreCache) ? 1 : 0;
              case typeIFloat:
                  {
                        double Result = m_Value.pFloat->GetValue(Verify, IgnoreCache);
                        if (Result > (int64_t)GC_INT64_MAX || Result < (int64_t)GC_INT64_MIN)
                            throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetValue(): Float value %f out of integer range", Result);
                        return round(Result);
                  }
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetValue(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IInteger interface
          inline void SetValue( int64_t Value, bool Verify = true)
          {
              switch(m_Type)
              {
              case typeValue:
                  m_Value.Value = Value;
                  break;
              case typeIInteger:
                  m_Value.pInteger->SetValue(Value, Verify);
                  break;
              case typeIEnumeration:
                  {
                      CEnumEntryPtr ptrOldEnumEntry;
                      double OldDistance = -1;
                      NodeList_t EnumEntries;
                      m_Value.pEnumeration->GetEntries(EnumEntries);
                      for( NodeList_t::iterator it=EnumEntries.begin(); it!=EnumEntries.end(); ++it )
                      {
                          if( IsAvailable(*it) )
                          {
                              if( !ptrOldEnumEntry.IsValid() )
                              {
                                  ptrOldEnumEntry = *it;
                                  OldDistance = abs( (double)Value - ptrOldEnumEntry->GetNumericValue() );
                              }
                              else
                              {
                                  CEnumEntryPtr ptrNewEnumEntry( *it );
                                  double  NewDistance = abs( (double)Value - ptrNewEnumEntry->GetNumericValue() ) ;
                                  if(NewDistance < OldDistance)
                                  {
                                      ptrOldEnumEntry = *it;
                                      OldDistance = NewDistance;
                                  }
                              }
                          }
                      }
                      if( ptrOldEnumEntry.IsValid() )
                          m_Value.pEnumeration->SetIntValue(ptrOldEnumEntry->GetValue(), Verify);
                      else
                          throw ACCESS_EXCEPTION("Failed to write enumeration. None of the entries is writable");
                  }
                  break;
              case typeIBoolean:
                  return m_Value.pBoolean->SetValue( (Value != 0), Verify);
                  break;
              case typeIFloat:
                  return m_Value.pFloat->SetValue( (double)Value, Verify);
                  break;
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::SetValue(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IInteger interface
          inline int64_t GetMin() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->GetMin();
              case typeIEnumeration:
              case typeIBoolean:
              case typeValue:
                  return GC_INT64_MIN;
              case typeIFloat:
                  {
                      double Min = m_Value.pFloat->GetMin();
                      if(Min > (int64_t)GC_INT64_MAX || Min < (int64_t)GC_INT64_MIN)
                          throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetMin(): Float value %f out of integer range", Min);
                      return round(Min);
                  }
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetMin(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IInteger interface
          inline int64_t GetMax() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->GetMax();
              case typeIEnumeration:
              case typeIBoolean:
              case typeValue:
                  return GC_INT64_MAX;
              case typeIFloat:
                  {
                      double Max = m_Value.pFloat->GetMax();
                      if(Max > (int64_t)GC_INT64_MAX || Max < (int64_t)GC_INT64_MIN)
                          throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetMin(): Float value %f out of integer range", Max);
                      return round(Max);
                  }
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetMax(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IInteger interface
          inline int64_t GetInc() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->GetInc();
              case typeIEnumeration:
              case typeIBoolean:
              case typeValue:
                  return 1;
              case typeIFloat:
                  if( m_Value.pFloat->HasInc() )
                      return round(m_Value.pFloat->GetInc());
                  else
                      return 1;
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetInc(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IInteger interface
          inline ERepresentation GetRepresentation() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->GetRepresentation();
              case typeValue:
              case typeIEnumeration:
              case typeIBoolean:
              case typeIFloat:
                  return PureNumber;
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetRepresentation(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IInteger interface
          GENICAM_NAMESPACE::gcstring GetUnit() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->GetUnit();
              case typeIFloat:
                  return m_Value.pFloat->GetUnit();
              case typeValue:
              case typeIEnumeration:
              case typeIBoolean:
                  return GENICAM_NAMESPACE::gcstring();
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetUnit(): uninitialized pointer");
              }
#pragma BullseyeCoverage on
          }

          //! see IValue interface
          bool IsValueCacheValid() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->IsValueCacheValid();
              case typeIEnumeration:
                  return m_Value.pEnumeration->IsValueCacheValid();
              case typeIBoolean:
                  return m_Value.pBoolean->IsValueCacheValid();
              case typeIFloat:
                  return m_Value.pFloat->IsValueCacheValid();
              case typeValue:
                  return true;
              case typeUninitialized:
#             pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::IsValueCacheValid(): uninitialized pointer");
              }
#             pragma BullseyeCoverage on
          }

        inline ECachingMode GetCachingMode() const
        {
            switch(m_Type)
            {
            case typeIInteger:
                return m_Value.pInteger->GetNode()->GetCachingMode();
            case typeIEnumeration:
                return m_Value.pEnumeration->GetNode()->GetCachingMode();
            case typeIBoolean:
                return m_Value.pBoolean->GetNode()->GetCachingMode();
            case typeIFloat:
                return m_Value.pFloat->GetNode()->GetCachingMode();
            case typeValue:
                return WriteThrough;
            case typeUninitialized:
            #pragma BullseyeCoverage off
            default:
                throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetCachingMode(): uninitialized pointer");
            #pragma BullseyeCoverage on
            }
        }

    protected:
        //! possible types of the internally held pointer
        typedef enum _EType
        {
            typeUninitialized,
            typeValue,
            typeIInteger,
            typeIEnumeration,
            typeIBoolean,
            typeIFloat
        } EType;

        //! the type of the internally held pointer
        EType m_Type;

        //! the place to store the value or the pointers to the nodes to get the value from
        union
        {
            int64_t Value;                //!> fixed value
            IInteger *pInteger;           //!> Integer node
            IEnumeration *pEnumeration;   //!> Enumeration node
            IBoolean *pBoolean;           //!> Boolean node
            IFloat *pFloat;               //!> Float node
        } m_Value;
    };


    //! A reference to a bool which can bei either an bool variable,
    //! or a pointer to an IInteger, an IEnumeration, or an IBoolean
    class CBooleanPolyRef
    {
    public:
        //! Constructor
        CBooleanPolyRef() :
          m_Type(typeUninitialized)
          {
              m_Value.Value = false;
          }

          #pragma BullseyeCoverage off
          GENICAM_NAMESPACE::gcstring GetName()  const
          {
              CNodePtr ptrNode = GetPointer();
              if( ptrNode.IsValid() )
                  return ptrNode->GetName();
              else
                  return GENICAM_NAMESPACE::gcstring(".Value.");
          }
          #pragma BullseyeCoverage on

          //! set integer value
          void operator=(bool Value)
          {
              m_Type = typeValue;
              m_Value.Value = Value;
          }

          //! set pointer
          void operator=(IBase *pValue)
          {
              m_Value.pInteger = dynamic_cast<IInteger*>(pValue);
              if( m_Value.pInteger )
                  m_Type = typeIInteger;
              else
              {
                  m_Value.pEnumeration = dynamic_cast<IEnumeration*>(pValue);
                  if( m_Value.pEnumeration )
                      m_Type = typeIEnumeration;
                  else
                  {
                      m_Value.pBoolean = dynamic_cast<IBoolean*>(pValue);
                      if( m_Value.pBoolean )
                          m_Type = typeIBoolean;
                      else
                          throw RUNTIME_EXCEPTION("CIntegerPolyRef::operator(IBase*) : pointer is neither IInteger*, IEnumeration*, nor IBoolean*");
                  }
              }
          }

          //! True if the object references a pointer
          inline bool IsPointer() const
          {
              return (m_Type != typeValue) && (m_Type != typeUninitialized);
          }

          //! True if the object is initilaized
          inline bool IsInitialized() const
          {
              return (m_Type != typeUninitialized);
          }

          //! returns the pointer referenced
          inline INodePrivate *GetPointer() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return dynamic_cast<INodePrivate*>(m_Value.pInteger);
              case typeIEnumeration:
                  return dynamic_cast<INodePrivate*>(m_Value.pEnumeration);
              case typeIBoolean:
                  return dynamic_cast<INodePrivate*>(m_Value.pBoolean);
              case typeValue:
                  return NULL;
#pragma BullseyeCoverage off
              case typeUninitialized:
              default:
                  assert(false);
                  return NULL;
#pragma BullseyeCoverage on
              }
          }

          //! cast to INode (may be zero)
          inline operator INode*(void) const
          {
              return GetPointer();
          }

          //! see IBoolean interface
          inline bool GetValue( bool Verify = false, bool IgnoreCache = false) const
          {
              switch(m_Type)
              {
              case typeValue:
                  return m_Value.Value;
              case typeIInteger:
                  return m_Value.pInteger->GetValue(Verify, IgnoreCache) != 0;
              case typeIEnumeration:
                  return m_Value.pEnumeration->GetIntValue(Verify, IgnoreCache) != 0;
              case typeIBoolean:
                  return m_Value.pBoolean->GetValue(Verify, IgnoreCache);
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::GetValue(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IBoolean interface
          inline void SetValue( bool Value, bool Verify = true)
          {
              switch(m_Type)
              {
              case typeValue:
                  m_Value.Value = Value;
                  break;
              case typeIInteger:
                  m_Value.pInteger->SetValue(Value ? 1 : 0, Verify);
                  break;
              case typeIEnumeration:
                  return m_Value.pEnumeration->SetIntValue(Value, Verify);
                  break;
              case typeIBoolean:
                  return m_Value.pBoolean->SetValue(Value, Verify);
                  break;
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::SetValue(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          inline ECachingMode GetCachingMode() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->GetNode()->GetCachingMode();
              case typeIEnumeration:
                  return m_Value.pEnumeration->GetNode()->GetCachingMode();
              case typeIBoolean:
                  return m_Value.pBoolean->GetNode()->GetCachingMode();
              case typeValue:
                  return WriteThrough;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CBooleanPolyRef::GetCachingMode(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }
    protected:
        //! possible types of the internally held pointer
        typedef enum _EType
        {
            typeUninitialized,
            typeValue,
            typeIInteger,
            typeIEnumeration,
            typeIBoolean
        } EType;

        //! the type of the internally held pointer
        EType m_Type;

        //! the place to store the value or the pointers to the nodes to get the value from
        union
        {
            bool Value;                   //!> fixed value
            IInteger *pInteger;           //!> Integer node
            IEnumeration *pEnumeration;   //!> Enumeration node
            IBoolean *pBoolean;           //!> Boolean node
        } m_Value;

    };

    //! A reference to a float which can be either a double variable,
    //! or a pointer to an IFloat, IInteger, or an IEnumeration interface
    class CFloatPolyRef
    {
    public:
        //! Constructor
        CFloatPolyRef() :
          m_Type(typeUninitialized)
          {
              m_Value.Value = 0.0;
          }

          //! set integer value
          void operator=(double Value)
          {
              m_Type = typeValue;
              m_Value.Value = Value;
          }
		  
		  //! set pointer
		  void operator=(INode *pValue)
		  {
			  operator=( dynamic_cast<IBase*>(pValue) );
		  }

          //! set pointer
          void operator=(IBase *pValue)
          {
              m_Value.pFloat = dynamic_cast<IFloat*>(pValue);
              if( m_Value.pFloat)
                  m_Type = typeIFloat;
              else
              {
                  m_Value.pEnumeration = dynamic_cast<IEnumeration*>(pValue);
                  if( m_Value.pEnumeration )
                      m_Type = typeIEnumeration;
                  else
                  {
                      m_Value.pInteger= dynamic_cast<IInteger*>(pValue);
                      if( m_Value.pInteger)
                          m_Type = typeIInteger;
                      else
                          throw RUNTIME_EXCEPTION("CFloatPolyRef::operator(IBase*) : pointer is neither IFloat*, IInteger*, nor IEnumeration*");
                  }
              }
          }

		  //! True if the object references a pointer
		  inline bool IsValue() const
		  {
			  return (m_Type == typeValue) && (m_Type != typeUninitialized);
		  }

          //! True if the object references a pointer
          inline bool IsPointer() const
          {
              return (m_Type != typeValue) && (m_Type != typeUninitialized);
          }

          //! True if the object is initialized
          inline bool IsInitialized() const
          {
              return (m_Type != typeUninitialized);
          }

          //! returns the pointer referenced
          inline INodePrivate *GetPointer() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return dynamic_cast<INodePrivate*>(m_Value.pFloat);
              case typeIInteger:
                  return dynamic_cast<INodePrivate*>(m_Value.pInteger);
              case typeIEnumeration:
                  return dynamic_cast<INodePrivate*>(m_Value.pEnumeration);
              case typeValue:
                  return NULL;
          #pragma BullseyeCoverage off
              case typeUninitialized:
              default:
                  assert(false);
                  return NULL;
          #pragma BullseyeCoverage on
              }
          }

          //! cast to INode (may be zero)
          inline operator INode*(void) const
          {
              return GetPointer();
          }

          //! see IFloat interface
          inline double GetValue( bool Verify = false, bool IgnoreCache = false) const
          {
              switch(m_Type)
              {
              case typeValue:
                  return m_Value.Value;
              case typeIFloat:
                  return m_Value.pFloat->GetValue(Verify, IgnoreCache);
              case typeIInteger:
                  return (double)m_Value.pInteger->GetValue(Verify, IgnoreCache);
              case typeIEnumeration:
                  {
                      CEnumEntryPtr ptrEnumEntry = m_Value.pEnumeration->GetCurrentEntry(Verify, IgnoreCache);
                      return ptrEnumEntry->GetNumericValue();
                  }
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetValue(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! see IFloat interface
          inline void SetValue( double Value, bool Verify = true)
          {
              switch(m_Type)
              {
              case typeValue:
                  m_Value.Value = Value;
                  break;
              case typeIFloat:
                  m_Value.pFloat->SetValue(Value, Verify);
                  break;
              case typeIInteger:
                  {
                      if( Value > (int64_t)GC_INT64_MAX || Value < (int64_t)GC_INT64_MIN  )
                          throw OUT_OF_RANGE_EXCEPTION("CIntegerPolyRef::SetValue(): double value outside int64 range");

                      int64_t TargetValue = round(Value);
                      int64_t Residuum = (TargetValue - m_Value.pInteger->GetMin()) % m_Value.pInteger->GetInc();
                      TargetValue -= Residuum;
                      if( 2 * Residuum > m_Value.pInteger->GetInc())
                          TargetValue += m_Value.pInteger->GetInc();
                      m_Value.pInteger->SetValue(TargetValue, Verify);
                  }
                  break;
              case typeIEnumeration:
                  {
                      CEnumEntryPtr ptrOldEnumEntry;
                      double OldDistance = -1;
                      NodeList_t EnumEntries;
                      m_Value.pEnumeration->GetEntries(EnumEntries);
                      for( NodeList_t::iterator it=EnumEntries.begin(); it!=EnumEntries.end(); ++it )
                      {
                          if( IsAvailable(*it) )
                          {
                              if( !ptrOldEnumEntry.IsValid() )
                              {
                                  ptrOldEnumEntry = *it;
                                  OldDistance = abs( Value - ptrOldEnumEntry->GetNumericValue() );
                              }
                              else
                              {
                                  CEnumEntryPtr ptrNewEnumEntry( *it );
                                  double  NewDistance = abs( Value - ptrNewEnumEntry->GetNumericValue() ) ;
                                  if(NewDistance < OldDistance)
                                  {
                                      ptrOldEnumEntry = *it;
                                      OldDistance = NewDistance;
                                  }
                              }
                          }
                      }
                      if( ptrOldEnumEntry.IsValid() )
                          m_Value.pEnumeration->SetIntValue(ptrOldEnumEntry->GetValue(), Verify);
                      else
                          throw ACCESS_EXCEPTION("Failed to write enumeration. None of the entries is writable");
                  }
                  break;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CIntegerPolyRef::SetValue(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! see IFloat interface
          inline double GetMin() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->GetMin();
              case typeIInteger:
                  return (double) m_Value.pInteger->GetMin();
              case typeIEnumeration:
              case typeValue:
                  return -std::numeric_limits<double>::max();
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetMin(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! see IFloat interface
          inline double GetMax() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->GetMax();
              case typeIInteger:
                  return (double) m_Value.pInteger->GetMax();
              case typeIEnumeration:
              case typeValue:
                  return std::numeric_limits<double>::max();
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetMax(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! True if the float has a constant increment
          inline bool HasInc()
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->HasInc();
              case typeIInteger:
                  return true;
              case typeIEnumeration:
              case typeValue:
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  return false;
              #pragma BullseyeCoverage on
              }
          }

          //! Get the constant increment if there is any
          virtual double GetInc()
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->GetInc();
              case typeIInteger:
                  return (double) m_Value.pInteger->GetInc();
              case typeIEnumeration:
              case typeValue:
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetInc(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! extension required for swiss knifes
          #pragma BullseyeCoverage off
          inline double GetInc() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return (double) m_Value.pInteger->GetInc();
              case typeIFloat:
              case typeIEnumeration:
              case typeValue:
                  return 1.0;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetMax(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }
          #pragma BullseyeCoverage on

          //! see IFloat interface
          inline ERepresentation GetRepresentation() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->GetRepresentation();
              case typeIInteger:
                  return m_Value.pInteger->GetRepresentation();
              case typeValue:
              case typeIEnumeration:
                  return PureNumber;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetRepresentation(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! see IFloat interface
          GENICAM_NAMESPACE::gcstring GetUnit() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->GetUnit();
              case typeIInteger:
                  return m_Value.pInteger->GetUnit();
              case typeValue:
              case typeIEnumeration:
                  return GENICAM_NAMESPACE::gcstring();
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetUnit(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

// this is currently not needed but may be in future so we keep the code
#if 0
          //! see IValue interface
          bool IsValueCacheValid() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->IsValueCacheValid();
              case typeIInteger:
                  return m_Value.pInteger->IsValueCacheValid();
              case typeIEnumeration:
                  return m_Value.pEnumeration->IsValueCacheValid();
              case typeValue:
                  return true;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::IsValueCacheValid(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }
#endif

          //! see IFloat
          EDisplayNotation GetDisplayNotation() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->GetDisplayNotation();
              case typeIInteger:
              case typeIEnumeration:
              case typeValue:
                  return fnAutomatic;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetDisplayNotation(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! see IFloat
          int64_t GetDisplayPrecision() const
          {
              switch(m_Type)
              {
              case typeIFloat:
                  return m_Value.pFloat->GetDisplayPrecision();
              case typeIInteger:
              case typeIEnumeration:
              case typeValue:
                  return -1;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetDisplayPrecision(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }

          //! possible types of the internally held pointer
          typedef enum _EType
          {
              typeUninitialized,
              typeValue,
              typeIFloat,
              typeIInteger,
              typeIEnumeration
          } EType;

          inline ECachingMode GetCachingMode() const
          {
              switch(m_Type)
              {
              case typeIInteger:
                  return m_Value.pInteger->GetNode()->GetCachingMode();
              case typeIEnumeration:
                  return m_Value.pEnumeration->GetNode()->GetCachingMode();
              case typeIFloat:
                  return m_Value.pFloat->GetNode()->GetCachingMode();
              case typeValue:
                  return WriteThrough;
              case typeUninitialized:
              #pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CFloatPolyRef::GetCachingMode(): uninitialized pointer");
              #pragma BullseyeCoverage on
              }
          }
    protected:
        //! the type of the internally held pointer
        EType m_Type;

        //! the place to store the value or the pointers to the nodes to get the value from
        union
        {
            double Value;                   //!> fixed value
            IFloat *pFloat;                 //!> Float node
            IInteger *pInteger;             //!> Integer node
            IEnumeration *pEnumeration;     //!> Enumeration node
        } m_Value;

    };


    //! A reference to a gcstring which can be either a gcstring variable,
    //! or a pointer to an IString
    class CStringPolyRef
    {
    public:
        //! Contructor
        CStringPolyRef() :
          m_Type(typeUninitialized)
          {
              m_Value.pString = NULL;
          }

          #pragma BullseyeCoverage off
          GENICAM_NAMESPACE::gcstring GetName() const
          {
              CNodePtr ptrNode = GetPointer();
              if( ptrNode.IsValid() )
                  return ptrNode->GetName();
              else
                  return GENICAM_NAMESPACE::gcstring(".Value.");
          }
          #pragma BullseyeCoverage on

          //! set string value
          void operator=(const GENICAM_NAMESPACE::gcstring &Value)
          {
              m_Type = typeValue;
              m_Value.Value = Value;
          }

          //! set pointer
          void operator=(IBase *pValue)
          {
              m_Value.pString = dynamic_cast<IString*>(pValue);
              if( m_Value.pString )
                  m_Type = typeIString;
              else
                  throw RUNTIME_EXCEPTION("CStringPolyRef::operator(IBase*) : pointer is not IString*");
          }

		  //! True if the object references a pointer
		  inline bool IsValue() const
		  {
			  return (m_Type == typeValue);
		  }


          //! True if the object references a pointer
          inline bool IsPointer() const
          {
              return (m_Type != typeValue) && (m_Type != typeUninitialized);
          }

          //! True if the object is initilaized
          inline bool IsInitialized() const
          {
              return (m_Type != typeUninitialized);
          }

          //! returns the pointer referenced
          inline INodePrivate *GetPointer() const
          {
              switch(m_Type)
              {
              case typeIString:
                  return dynamic_cast<INodePrivate*>(m_Value.pString);
              case typeValue:
                  return NULL;
#           pragma BullseyeCoverage off
              case typeUninitialized:
              default:
                  assert(false);
                  return NULL;
#           pragma BullseyeCoverage on
              }
          }

          //! cast to INode (may be zero)
          inline operator INode*(void) const
          {
              return GetPointer();
          }

          //! see IString interface
          inline GENICAM_NAMESPACE::gcstring GetValue( bool Verify = false, bool IgnoreCache = false) const
          {
              switch(m_Type)
              {
              case typeValue:
                  return m_Value.Value;
              case typeIString:
                  return m_Value.pString->GetValue(Verify, IgnoreCache);
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CStringPolyRef::GetValue(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IString interface
          inline void SetValue( const GENICAM_NAMESPACE::gcstring& Value, bool Verify = true)
          {
              switch(m_Type)
              {
              case typeValue:
                  m_Value.Value = Value;
                  break;
              case typeIString:
                  m_Value.pString->SetValue(Value, Verify);
                  break;
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CStringPolyRef::SetValue(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }

          //! see IString interface
          inline int64_t GetMaxLength( )
          {
              switch(m_Type)
              {
              case typeValue:
                  return m_Value.Value.max_size();
                  break;
              case typeIString:
                  return m_Value.pString->GetMaxLength();
                  break;
              case typeUninitialized:
#pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CStringPolyRef::GetMaxLength(): uninitialized pointer");
#pragma BullseyeCoverage on
              }
          }


          //! see IValue interface
          bool IsValueCacheValid() const
          {
              switch(m_Type)
              {
              case typeIString:
                  return m_Value.pString->IsValueCacheValid();
              case typeValue:
                  return true;
              case typeUninitialized:
#             pragma BullseyeCoverage off
              default:
                  throw RUNTIME_EXCEPTION("CStringPolyRef::IsValueCacheValid(): uninitialized pointer");
              }
#             pragma BullseyeCoverage on
          }


    protected:
        //! possible types of the internally held pointer
        typedef enum _EType
        {
            typeUninitialized,
            typeValue,
            typeIString
        } EType;

        //! the type of the internally held pointer
        EType m_Type;

        //! the place to store the value or the pointers to the nodes to get the value from
        struct
        {
            GENICAM_NAMESPACE::gcstring Value;      //!> fixed value
            IString *pString;             //!> String node
        } m_Value;
    };

	class CIntegerOffsetPolyRef
	{
	public:
		CIntegerOffsetPolyRef() 
		{
		};
		CIntegerOffsetPolyRef( INode *_pIndex, int64_t _Offset ) 
		{
			pIndex = _pIndex;
			Offset = _Offset;
		};

		CIntegerOffsetPolyRef( INode *_pIndex, INode *_pOffset ) 
		{
			pIndex = _pIndex;
			Offset = _pOffset;
		};

		CIntegerOffsetPolyRef( const CIntegerOffsetPolyRef &Copy ) 
		{
			pIndex = Copy.pIndex;
			Offset = Copy.Offset;
		};

		CIntegerPolyRef pIndex;
		CIntegerPolyRef Offset;
	}; 


}

#endif // ifndef GENAPI_POLYREFERENCE_H
