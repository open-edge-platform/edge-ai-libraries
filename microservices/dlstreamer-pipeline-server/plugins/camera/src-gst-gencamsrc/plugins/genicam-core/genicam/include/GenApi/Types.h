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
\brief Common types used in the public GenApi interface.
\ingroup GenApi_PublicUtilities
*/

#ifndef GENAPI_TYPES_H
#define GENAPI_TYPES_H

#include <Base/GCTypes.h>
#include <Base/GCStringVector.h>
#include <GenApi/GenApiDll.h>
#include <GenApi/Autovector.h>
#include <GenICamFwd.h>

namespace GENAPI_NAMESPACE
{

    //! signed or unsigned integers
    //! \ingroup GenApi_PublicUtilities
    typedef enum _ESign
    {
        Signed,         //!< Integer is signed
        Unsigned,       //!< Integer is unsigned
        _UndefinedSign  //!< Object is not yet initialized
    } ESign;

    //! access mode of a node
    //! \ingroup GenApi_PublicUtilities
    typedef enum _EAccessMode
    {
        NI,        //!< Not implemented
        NA,        //!< Not available
        WO,        //!< Write Only
        RO,        //!< Read Only
        RW,        //!< Read and Write
        _UndefinedAccesMode,    //!< Object is not yet initialized
        _CycleDetectAccesMode   //!< used internally for AccessMode cycle detection

    } EAccessMode;

    //! recommended visibility of a node
    //! \ingroup GenApi_PublicUtilities
    typedef enum _EVisibility
    {
        Beginner = 0,              //!< Always visible
        Expert = 1,                //!< Visible for experts or Gurus
        Guru = 2,                  //!< Visible for Gurus
        Invisible = 3,             //!< Not Visible
        _UndefinedVisibility  = 99 //!< Object is not yet initialized
    } EVisibility;

    //! caching mode of a register
    //! \ingroup GenApi_PublicUtilities
    typedef enum _ECachingMode
    {
        NoCache,              //!< Do not use cache
        WriteThrough,         //!< Write to cache and register
        WriteAround,          //!< Write to register, write to cache on read
        _UndefinedCachingMode //!< Not yet initialized
    } ECachingMode;

    //! recommended representation of a node value
    //! \ingroup GenApi_PublicUtilities
    typedef enum _ERepresentation
    {
        Linear,                     //!< Slider with linear behavior
        Logarithmic,                //!< Slider with logarithmic behaviour
        Boolean,                    //!< Check box
        PureNumber,                 //!< Decimal number in an edit control
        HexNumber,                  //!< Hex number in an edit control
        IPV4Address,                //!< IP-Address
        MACAddress,                 //!< MAC-Address
        _UndefinedRepresentation
    } ERepresentation;

// this define is required to deal with a spelling error corrected in v1.2
#ifndef NO_UNDEFINEDED_REPRESENTATION
#   define _UndefindedRepresentation _UndefinedRepresentation
#endif

    //! Endianess of a value in a register
    //! \ingroup GenApi_PublicUtilities
    typedef enum _EEndianess
    {
        BigEndian,        //!< Register is big endian
        LittleEndian,     //!< Register is little endian
        _UndefinedEndian  //!< Object is not yet initialized
    } EEndianess;


    //! Defines if a node name is standard or custom
    //! \ingroup GenApi_PublicUtilities
    typedef enum _ENameSpace
    {
        Custom,             //!< name resides in custom namespace
        Standard,           //!< name resides in one of the standard namespaces
        _UndefinedNameSpace //!< Object is not yet initialized
    } ENameSpace;


    //! Defines from which standard namespace a node name comes from
    //! \ingroup GenApi_PublicUtilities
    typedef enum _EStandardNameSpace
    {
        None,            //!< name resides in custom namespace
        GEV,             //!< name resides in GigE Vision namespace
        IIDC,            //!< name resides in 1394 IIDC namespace
        CL,              //!< name resides in camera link namespace
        USB,             //!< name resides in USB namespace
        _UndefinedStandardNameSpace  //!< Object is not yet initialized
    } EStandardNameSpace;


    //! Defines the choices of a Yes/No alternatives
    //! \ingroup GenApi_PublicUtilities
    typedef enum _EYesNo
    {
        Yes = 1,                //!< yes
        No = 0,                 //!< no
        _UndefinedYesNo = 2     //!< Object is not yet initialized
    } EYesNo;

    //! A list of strings
    //! \ingroup GenApi_PublicImpl
    typedef GENICAM_NAMESPACE::gcstring_vector StringList_t;


    //! typedef for formula type
    //! \ingroup GenApi_PublicImpl
    typedef enum _ESlope
    {
        Increasing,      //!< strictly monotonous increasing
        Decreasing,      //!< strictly monotonous decreasing
        Varying,         //!< slope changes, e.g. at run-time
        Automatic,       //!< slope is determined automatically by probing the function
        _UndefinedESlope //!< Object is not yet initialized
    } ESlope;

    //! typedef describing the different validity checks which can be performed on an XML file
    /*! The enum values for a bitfield of length uint32_t */
    //! \ingroup GenApi_PublicImpl
    typedef enum _EXMLValidation
    {
        xvLoad      = 0x00000001L,    //!< Creates a dummy node map
        xvCycles    = 0x00000002L,    //!< checks for write and dependency cycles (implies xvLoad)
        xvSFNC      = 0x00000004L,    //!< checks for conformance with the standard feature naming convention (SFNC)
        xvDefault   = 0x00000000L,    //!< checks performed if nothing else is said
        xvAll       = 0xffffffffL,    //!< all possible checks
        _UndefinedEXMLValidation = 0x8000000L //!< Object is not yet initialized
    } EXMLValidation;

    //! typedef for float notation
    //! \ingroup GenApi_PublicImpl
    typedef enum _EDisplayNotation
    {
        fnAutomatic,                //!< the notation if either scientific or fixed depending on what is shorter
        fnFixed,                    //!< the notation is fixed, e.g. 123.4
        fnScientific,               //!< the notation is scientific, e.g. 1.234e2
        _UndefinedEDisplayNotation  //!< Object is not yet initialized
    } EDisplayNotation;

    //! typedef for interface type
    //! \ingroup GenApi_PublicImpl
    typedef enum _EInterfaceType
    {
        intfIValue,       //!< IValue interface
        intfIBase,        //!< IBase interface
        intfIInteger,     //!< IInteger interface
        intfIBoolean,     //!< IBoolean interface
        intfICommand,     //!< ICommand interface
        intfIFloat,       //!< IFloat interface
        intfIString,      //!< IString interface
        intfIRegister,    //!< IRegister interface
        intfICategory,    //!< ICategory interface
        intfIEnumeration, //!< IEnumeration interface
        intfIEnumEntry,   //!< IEnumEntry interface
        intfIPort         //!< IPort interface
    } EInterfaceType;

    //! typedef for link type
    /*! For details see GenICam Wiki : GenApi/SoftwareArchitecture/NodeDependencies
    \ingroup GenApi_PublicImpl
    */
    typedef enum _ELinkType
    {
        ctParentNodes,          //!< All nodes for which this node is at least an invalidating child
        ctReadingChildren,      //!< All nodes which can be read from 
        ctWritingChildren,      //!< All nodes which can write a value further down the node stack
        ctInvalidatingChildren, //!< All directly connected nodes which invalidate this node
        ctDependingNodes,       //!< All directly or indirectly connected nodes which are invalidated by this nodes (i.e. which are dependent on this node)
        ctTerminalNodes,         //!< All indirectly connected terminal nodes
        ctValueChangingChildren  //!< All child node used to compute the value.
    } ELinkType;

    //! typedef for increment mode
    //! \ingroup GenApi_PublicImpl
    typedef enum _EIncMode
    {
        noIncrement,    // !> The feature has no increment
        fixedIncrement, // !> The feature has a fix increment
        listIncrement   // !> The feature has a list of valid value
    } EIncMode;

    //! typedef for link type
    //! \ingroup GenApi_PublicImpl
    typedef enum _EInputDirection
    {
        idFrom, //!< Indicates a swiss knife that it is used as worker for a converter computing FROM
        idTo,   //!< Indicates a swiss knife that it is used as worker for a converter computing TO
        idNone  //!< SwissKnife is not used within a converter
    } EInputDirection;

    //! GenApi schema version
    typedef enum _EGenApiSchemaVersion
    {
        v1_0 = 1,
        v1_1 = 2,
        _Undefined = -1
    } EGenApiSchemaVersion;

}

#endif // ifndef GENAPI_TYPES_H
