"""
Editor Tools for Unreal MCP.

This module provides tools for controlling the Unreal Editor viewport and other editor functionality.
"""

import logging
from typing import Dict, List, Any, Optional
from mcp.server.fastmcp import FastMCP, Context
from tools._bridge_validation import require_unreal_success
from tools._bridge_validation import require_unreal_success

# Get logger
logger = logging.getLogger("UnrealMCP")

def register_editor_tools(mcp: FastMCP):
    """Register editor tools with the MCP server."""
    
    @mcp.tool()
    def get_actors_in_level(ctx: Context) -> List[Dict[str, Any]]:
        """List actors in the connected Unreal level.

        A disconnected or invalid response is an error, NEVER an empty level.
        SDK v1 maps raised tool exceptions to CallToolResult(isError=True).
        """
        from unreal_mcp_server import get_unreal_connection

        try:
            unreal = get_unreal_connection()
            if unreal is None:
                raise ConnectionError("Cannot inspect level: Unreal connection unavailable")

            response = unreal.send_command("get_actors_in_level", {})
            if not response:
                raise ConnectionError("Cannot inspect level: no response from Unreal")

            if response.get("status") == "error" or response.get("success") is False:
                raise RuntimeError(
                    "Cannot inspect level: "
                    + str(response.get("error") or response.get("message") or "Unreal reported an error")
                )

            if isinstance(response.get("result"), dict) and isinstance(response["result"].get("actors"), list):
                actors = response["result"]["actors"]
            elif isinstance(response.get("actors"), list):
                actors = response["actors"]
            else:
                raise ValueError("Cannot inspect level: invalid actors response from Unreal")

            logger.info("Found %d actors in level", len(actors))
            return actors

        except Exception as e:
            logger.error("Actor lookup failed: %s", e)
            raise

    @mcp.tool()
    def find_actors_by_name(ctx: Context, pattern: str) -> List[str]:
        """Return matching actor names; never mistake a connection failure for no matches."""
        from unreal_mcp_server import get_unreal_connection

        try:
            unreal = get_unreal_connection()
            if unreal is None:
                raise ConnectionError("Unreal connection unavailable")
            response = require_unreal_success(
                "find_actors_by_name",
                unreal.send_command("find_actors_by_name", {"pattern": pattern}),
            )
            actors = response["result"].get("actors")
            if not isinstance(actors, list):
                raise ValueError("find_actors_by_name: missing actors list")
            if not all(isinstance(actor, dict) and isinstance(actor.get("name"), str) for actor in actors):
                raise ValueError("find_actors_by_name: invalid actor record")
            return [actor["name"] for actor in actors]
        except Exception:
            logger.exception("Failed to search Unreal actors")
            raise

    @mcp.tool()
    def spawn_actor(
        ctx: Context,
        name: str,
        type: str,
        location: List[float] = [0.0, 0.0, 0.0],
        rotation: List[float] = [0.0, 0.0, 0.0]
    ) -> Dict[str, Any]:
        """Create a new actor in the current level.
        
        Args:
            ctx: The MCP context
            name: The name to give the new actor (must be unique)
            type: The type of actor to create (e.g. StaticMeshActor, PointLight)
            location: The [x, y, z] world location to spawn at
            rotation: The [pitch, yaw, roll] rotation in degrees
            
        Returns:
            Dict containing the created actor's properties
        """
        from unreal_mcp_server import get_unreal_connection
        
        try:
            unreal = get_unreal_connection()
            if not unreal:
                logger.error("Failed to connect to Unreal Engine")
                raise RuntimeError("Failed to connect to Unreal Engine")
            
            # Ensure all parameters are properly formatted
            params = {
                "name": name,
                "type": type.upper(),  # Make sure type is uppercase
                "location": location,
                "rotation": rotation
            }
            
            # Validate location and rotation formats
            for param_name in ["location", "rotation"]:
                param_value = params[param_name]
                if not isinstance(param_value, list) or len(param_value) != 3:
                    logger.error(f"Invalid {param_name} format: {param_value}. Must be a list of 3 float values.")
                    raise RuntimeError(f"Invalid {param_name} format. Must be a list of 3 float values.")
                # Ensure all values are float
                params[param_name] = [float(val) for val in param_value]
            
            logger.info(f"Creating actor '{name}' of type '{type}' with params: {params}")
            response = unreal.send_command("spawn_actor", params)
            response = require_unreal_success("spawn_actor", response)
            
            if not response:
                logger.error("No response from Unreal Engine")
                raise RuntimeError("No response from Unreal Engine")
            
            # Log the complete response for debugging
            logger.info(f"Actor creation response: {response}")
            
            # Handle error responses correctly
            if response.get("status") == "error":
                error_message = response.get("error", "Unknown error")
                logger.error(f"Error creating actor: {error_message}")
                raise RuntimeError(error_message)
            
            return response
            
        except Exception as e:
            error_msg = f"Error creating actor: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    @mcp.tool()
    def delete_actor(ctx: Context, name: str) -> Dict[str, Any]:
        """Delete a named actor; failures must surface as MCP tool errors."""
        from unreal_mcp_server import get_unreal_connection

        try:
            unreal = get_unreal_connection()
            if unreal is None:
                raise ConnectionError("Unreal connection unavailable")
            return require_unreal_success(
                "delete_actor", unreal.send_command("delete_actor", {"name": name})
            )
        except Exception:
            logger.exception("Failed to delete Unreal actor")
            raise

    @mcp.tool()
    def set_actor_transform(
        ctx: Context,
        name: str,
        location: List[float]  = None,
        rotation: List[float]  = None,
        scale: List[float] = None
    ) -> Dict[str, Any]:
        """Set the transform of an actor."""
        from unreal_mcp_server import get_unreal_connection
        
        try:
            unreal = get_unreal_connection()
            if not unreal:
                logger.error("Failed to connect to Unreal Engine")
                raise RuntimeError("Failed to connect to Unreal Engine")
                
            params = {"name": name}
            if location is not None:
                params["location"] = location
            if rotation is not None:
                params["rotation"] = rotation
            if scale is not None:
                params["scale"] = scale
                
            response = unreal.send_command("set_actor_transform", params)
            response = require_unreal_success("set_actor_transform", response)
            return response
            
        except Exception as e:
            logger.error(f"Error setting transform: {e}")
            raise RuntimeError("Unreal tool returned an empty or invalid response")
    
    @mcp.tool()
    def get_actor_properties(ctx: Context, name: str) -> Dict[str, Any]:
        """Get all properties of an actor."""
        from unreal_mcp_server import get_unreal_connection
        
        try:
            unreal = get_unreal_connection()
            if not unreal:
                logger.error("Failed to connect to Unreal Engine")
                raise RuntimeError("Failed to connect to Unreal Engine")
                
            response = unreal.send_command("get_actor_properties", {
                "name": name
            })
            response = require_unreal_success("get_actor_properties", response)
            return response
            
        except Exception as e:
            logger.error(f"Error getting properties: {e}")
            raise RuntimeError("Unreal tool returned an empty or invalid response")

    @mcp.tool()
    def set_actor_property(
        ctx: Context,
        name: str,
        property_name: str,
        property_value,
    ) -> Dict[str, Any]:
        """
        Set a property on an actor.
        
        Args:
            name: Name of the actor
            property_name: Name of the property to set
            property_value: Value to set the property to
            
        Returns:
            Dict containing response from Unreal with operation status
        """
        from unreal_mcp_server import get_unreal_connection
        
        try:
            unreal = get_unreal_connection()
            if not unreal:
                logger.error("Failed to connect to Unreal Engine")
                raise RuntimeError("Failed to connect to Unreal Engine")
                
            response = unreal.send_command("set_actor_property", {
                "name": name,
                "property_name": property_name,
                "property_value": property_value
            })
            response = require_unreal_success("set_actor_property", response)
            
            if not response:
                logger.error("No response from Unreal Engine")
                raise RuntimeError("No response from Unreal Engine")
            
            logger.info(f"Set actor property response: {response}")
            return response
            
        except Exception as e:
            error_msg = f"Error setting actor property: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    # @mcp.tool() commented out because it's buggy
    def focus_viewport(
        ctx: Context,
        target: str = None,
        location: List[float] = None,
        distance: float = 1000.0,
        orientation: List[float] = None
    ) -> Dict[str, Any]:
        """
        Focus the viewport on a specific actor or location.
        
        Args:
            target: Name of the actor to focus on (if provided, location is ignored)
            location: [X, Y, Z] coordinates to focus on (used if target is None)
            distance: Distance from the target/location
            orientation: Optional [Pitch, Yaw, Roll] for the viewport camera
            
        Returns:
            Response from Unreal Engine
        """
        from unreal_mcp_server import get_unreal_connection
        
        try:
            unreal = get_unreal_connection()
            if not unreal:
                logger.error("Failed to connect to Unreal Engine")
                raise RuntimeError("Failed to connect to Unreal Engine")
                
            params = {}
            if target:
                params["target"] = target
            elif location:
                params["location"] = location
            
            if distance:
                params["distance"] = distance
                
            if orientation:
                params["orientation"] = orientation
                
            response = unreal.send_command("focus_viewport", params)
            response = require_unreal_success("focus_viewport", response)
            return response
            
        except Exception as e:
            logger.error(f"Error focusing viewport: {e}")
            raise RuntimeError(str(e))

    @mcp.tool()
    def spawn_blueprint_actor(
        ctx: Context,
        blueprint_name: str,
        actor_name: str,
        location: List[float] = [0.0, 0.0, 0.0],
        rotation: List[float] = [0.0, 0.0, 0.0]
    ) -> Dict[str, Any]:
        """Spawn an actor from a Blueprint.
        
        Args:
            ctx: The MCP context
            blueprint_name: Name of the Blueprint to spawn from
            actor_name: Name to give the spawned actor
            location: The [x, y, z] world location to spawn at
            rotation: The [pitch, yaw, roll] rotation in degrees
            
        Returns:
            Dict containing the spawned actor's properties
        """
        from unreal_mcp_server import get_unreal_connection
        
        try:
            unreal = get_unreal_connection()
            if not unreal:
                logger.error("Failed to connect to Unreal Engine")
                raise RuntimeError("Failed to connect to Unreal Engine")
            
            # Ensure all parameters are properly formatted
            params = {
                "blueprint_name": blueprint_name,
                "actor_name": actor_name,
                "location": location or [0.0, 0.0, 0.0],
                "rotation": rotation or [0.0, 0.0, 0.0]
            }
            
            # Validate location and rotation formats
            for param_name in ["location", "rotation"]:
                param_value = params[param_name]
                if not isinstance(param_value, list) or len(param_value) != 3:
                    logger.error(f"Invalid {param_name} format: {param_value}. Must be a list of 3 float values.")
                    raise RuntimeError(f"Invalid {param_name} format. Must be a list of 3 float values.")
                # Ensure all values are float
                params[param_name] = [float(val) for val in param_value]
            
            logger.info(f"Spawning blueprint actor with params: {params}")
            response = unreal.send_command("spawn_blueprint_actor", params)
            response = require_unreal_success("spawn_blueprint_actor", response)
            
            if not response:
                logger.error("No response from Unreal Engine")
                raise RuntimeError("No response from Unreal Engine")
            
            logger.info(f"Spawn blueprint actor response: {response}")
            return response
            
        except Exception as e:
            error_msg = f"Error spawning blueprint actor: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    logger.info("Editor tools registered successfully")
